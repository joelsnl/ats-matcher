"""Provider behavior and failure regressions. All upstream responses are fixtures."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from email.message import Message
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import pytest
from typer.testing import CliRunner

from ats_matcher.cli import app
from ats_matcher.config import Settings
from ats_matcher.jobs.ats_detector import ATSDetector
from ats_matcher.jobs.base import ProviderError
from ats_matcher.jobs.company_registry import CompanyRegistry
from ats_matcher.jobs.providers.ashby import AshbyProvider
from ats_matcher.jobs.providers.ats import _matches, make_job
from ats_matcher.jobs.providers.freehire import FreehireProvider
from ats_matcher.jobs.providers.greenhouse import GreenhouseProvider
from ats_matcher.jobs.providers.indeed import IndeedProvider
from ats_matcher.jobs.providers.lever import LeverProvider
from ats_matcher.jobs.providers.public_api import PublicAPI, fetch_json
from ats_matcher.jobs.registry import default_registry, ProviderRegistry
from ats_matcher.jobs.service import JobSearchService
from ats_matcher.schemas.jobs import JobSearchQuery

NOW = datetime(2026, 9, 15, tzinfo=timezone.utc)


def query(**kwargs):
    return JobSearchQuery(**{"keywords": "engineer", "date_since_posted": "any", **kwargs})


def posting(n=1, **kwargs):
    return {"id": n, "title": "Software Engineer", "absolute_url": f"https://example.com/jobs/{n}",
            "location": {"name": "Berlin"}, "first_published": "2026-09-14T12:00:00Z",
            "content": "&lt;p&gt;Python and SQL&lt;/p&gt;", **kwargs}


def greenhouse(rows=None, **kwargs):
    return GreenhouseProvider(boards=["stripe"], delay=0, now=lambda: NOW,
                              fetch=lambda url, timeout: {"jobs": rows if rows is not None else [posting()]}, **kwargs)


@pytest.mark.parametrize("url", [
    "https://boards.greenhouse.io.evil.test/stripe",
    "https://evil.test/boards.greenhouse.io/stripe",
    "https://user@boards.greenhouse.io/stripe",
    "ftp://boards.greenhouse.io/stripe",
    "https://boards.greenhouse.io",
    "https://api.lever.co/other/postings/acme",
    "https://boards.greenhouse.io/%2e%2e",
    "https://boards.greenhouse.io/stripe?redirect=https://evil.test",  # Query cannot change the detected board.
])
def test_detection_uses_host_boundaries(url):
    result = ATSDetector.detect(url)
    assert result == (("greenhouse", "stripe") if "?redirect" in url else None)


@pytest.mark.parametrize("url, expected", [
    ("https://job-boards.greenhouse.io/Acme/jobs/1", ("greenhouse", "Acme")),
    ("https://api.lever.co/v0/postings/Acme", ("lever", "Acme")),
    ("https://jobs.eu.lever.co/Acme/1", ("lever", "eu:Acme")),
    ("https://tenant.wd5.myworkdayjobs.com/en-US/Careers", ("workday", "tenant")),
    ("https://api.ashbyhq.com/posting-api/job-board/Acme", ("ashby", "Acme")),
])
def test_detect_board_tokens(url, expected):
    assert ATSDetector.detect(url) == expected


def test_unsupported_detection_does_not_advertise_provider():
    assert ATSDetector.suggest_providers("https://tenant.wd5.myworkdayjobs.com/Careers") == []


def test_company_search_has_no_duplicates_or_blank_matches():
    registry = CompanyRegistry()
    assert [c.slug for c in registry.search(" Stripe ")] == ["stripe"]
    assert registry.search(" ") == []
    assert registry.get_by_board("lever", "palantir").name == "Palantir Technologies"


def test_configured_boards_and_empty_override():
    registry = default_registry(Settings(JOBS_GREENHOUSE_BOARDS="acme, example,acme", JOBS_LEVER_BOARDS=""))
    assert registry.get("greenhouse").boards == ("acme", "example")
    assert registry.get("lever").boards == ()
    with pytest.raises(ProviderError, match="No lever"):
        registry.get("lever").search(query())


def test_board_ids_are_scoped_and_invalid_records_are_reported():
    provider = GreenhouseProvider(boards=["one", "two"], delay=0, fetch=lambda url, timeout: {"jobs": [posting(), posting(), None, {"title": "Bad"}]})
    result = provider.search(query())
    assert [job.job_id for job in result.jobs] == ["greenhouse:one:1", "greenhouse:two:1"]
    assert result.status == "partial" and "4" in result.warnings[0]
    assert result.returned == 2 and result.pages_fetched == 2


def test_html_skills_date_and_description_opt_out():
    job = greenhouse().search(query()).jobs[0]
    assert job.description == "Python and SQL"
    assert {"Python", "SQL"} <= set(job.skills)
    assert job.posted_at == "2026-09-14T12:00:00Z"
    assert greenhouse(fetch_descriptions=False).search(query()).jobs[0].description is None
    job = greenhouse([posting(first_published=None, updated_at="2026-09-15")])._job(posting(first_published=None), "stripe")
    assert job.posted_at is None


def test_date_filter_excludes_old_and_unknown_not_updated_date():
    rows = [posting(1), posting(2, first_published="2020-01-01"), posting(3, first_published=None)]
    result = greenhouse(rows).search(query(date_since_posted="past_week"))
    assert [job.job_id for job in result.jobs] == ["greenhouse:stripe:1"]
    assert "without a publication date" in result.warnings[0]


def test_filters_do_not_accept_missing_fields_or_description_location():
    job = make_job(title="Software Engineer", company="Acme", location="Paris", url="https://example.com",
                   job_id="1", source="test", description="Our Berlin office uses Python")
    assert not _matches(job, query(location="Berlin"))
    assert not _matches(job, query(workplace_type=["remote", "hybrid"]))
    assert not _matches(job, query(job_type="full_time"))
    assert _matches(job, query(keywords='"Data Analyst" OR "Software Engineer"'))


def test_limit_cache_key_and_nonoverlapping_pagination():
    provider = greenhouse([posting(n) for n in range(5)])
    first = provider.search(query(limit=2))
    assert first.next_page == 1 and first.returned == 2
    second = provider.search(query(limit=2, page=1))
    assert {j.job_id for j in first.jobs}.isdisjoint(j.job_id for j in second.jobs)
    assert provider.search(query(limit=2), limit=4).returned == 4
    cached = provider.search(query(limit=2))
    assert cached.cached
    cached.jobs.clear()
    assert provider.search(query(limit=2)).returned == 2


def test_sort_before_limit_and_actual_request_budget():
    provider = greenhouse([posting(1, first_published="2020-01-01"), posting(2)])
    assert provider.search(query(limit=1, sort_by="recent")).jobs[0].job_id.endswith(":2")
    provider = GreenhouseProvider(boards=["one", "two"], max_pages=1, delay=0, fetch=lambda url, timeout: {"jobs": []})
    result = provider.search(query())
    assert result.pages_fetched == 1 and result.status == "partial"


def test_partial_board_failure_is_not_cached_and_all_failures_are_errors():
    calls = []
    def fetch(url, timeout):
        calls.append(url)
        if "/bad/" in url:
            raise HTTPError(url, 404, "missing", {}, None)
        return {"jobs": []}
    provider = GreenhouseProvider(boards=["stripe", "bad"], delay=0, fetch=fetch)
    result = provider.search(query())
    assert result.status == "partial" and result.returned == 0
    provider.search(query())
    assert len(calls) == 4
    provider = GreenhouseProvider(boards=["bad"], delay=0, fetch=fetch)
    result = provider.search(query())
    assert result.status == "error" and result.error_code == "board_not_found" and result.error


@pytest.mark.parametrize("payload", [None, {}, {"jobs": None}, {"jobs": {}}])
def test_malformed_payload_is_not_empty_success(payload):
    provider = GreenhouseProvider(boards=["stripe"], delay=0, fetch=lambda url, timeout: payload)
    assert provider.search(query()).error_code == "invalid_response"


def test_bad_filters_fail_before_network():
    provider = greenhouse()
    with pytest.raises(ProviderError, match="salary"):
        provider.search(query(salary=40000))


def test_public_api_retry_after_and_access_denied():
    calls, sleeps = [], []
    headers = Message()
    headers["Retry-After"] = "4"
    def fetch(url, timeout):
        calls.append(url)
        if len(calls) == 1:
            raise HTTPError(url, 429, "rate limited", headers, None)
        return {"jobs": []}
    api = PublicAPI(fetch=fetch, sleep=sleeps.append, delay=0)
    assert api.request("https://example.com") == {"jobs": []}
    assert 4 in sleeps and len(calls) == 2
    def denied(url, timeout):
        raise HTTPError(url, 403, "denied", {}, None)
    with pytest.raises(ProviderError) as error:
        PublicAPI(fetch=denied, sleep=sleeps.append).request("https://example.com")
    assert error.value.code == "access_denied"


def test_transport_invalid_json_and_response_bound(monkeypatch):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit): return b"<html>blocked</html>"
    class Opener:
        def open(self, *args, **kwargs): return Response()
    monkeypatch.setattr("ats_matcher.jobs.providers.public_api.build_opener", lambda *args: Opener())
    with pytest.raises(ProviderError, match="valid JSON"):
        fetch_json("https://example.com", 1)
    monkeypatch.setattr("ats_matcher.jobs.providers.public_api.MAX_RESPONSE_BYTES", 3)
    with pytest.raises(ProviderError, match="size limit"):
        fetch_json("https://example.com", 1)


def test_lever_includes_requirements_and_correct_workplace():
    provider = LeverProvider()
    job = provider._job({"id": "a", "text": "Engineer", "hostedUrl": "https://jobs.lever.co/spotify/a",
        "categories": {"location": "Paris", "allLocations": ["Paris", "Berlin"], "commitment": "Full-time"},
        "workplaceType": "remote", "descriptionPlain": "Build products",
        "lists": [{"text": "Requirements", "content": "<li>Python</li>"}],
        "additionalPlain": "Benefits", "createdAt": 1789430400000}, "spotify")
    assert job.workplace_type == "remote" and job.employment_type == "full_time"
    assert "Berlin" in job.location and "Python" in job.description and "Benefits" in job.description
    assert "api.eu.lever.co" in provider._url("eu:Acme")


def test_ashby_employment_and_secondary_locations():
    provider = AshbyProvider()
    record = {"title": "Engineer", "jobUrl": "https://jobs.ashbyhq.com/openai/1", "location": "London",
              "secondaryLocations": [{"location": "Berlin"}], "workplaceType": "OnSite", "employmentType": "FullTime"}
    job = provider._job(record, "openai")
    assert job.employment_type == "full_time" and job.workplace_type == "on_site" and "Berlin" in job.location
    assert provider._job({**record, "isListed": False}, "openai") is None


def test_career_url_routes_service_and_cli(monkeypatch):
    calls = []
    provider = GreenhouseProvider(boards=[], delay=0, fetch=lambda url, timeout: calls.append(url) or {"jobs": [posting()]})
    registry = ProviderRegistry()
    registry.register("greenhouse", lambda: provider)
    service = JobSearchService(registry, settings=Settings(JOBS_TRANSLATE=False))
    result = service.search(query(career_url="https://job-boards.greenhouse.io/Acme"))
    assert result.jobs[0].job_id == "greenhouse:Acme:1"
    assert "/boards/Acme/jobs" in calls[0]
    with pytest.raises(ValueError, match="match"):
        service.search(query(career_url="https://boards.greenhouse.io/Acme"), ["linkedin"])
    monkeypatch.setattr("ats_matcher.cli.JobSearchService", lambda: service)
    result = CliRunner().invoke(app, ["search", "--keyword", "engineer", "--career-url", "https://boards.greenhouse.io/Acme", "--date", "any", "--no-translate"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["jobs_meta"]["provider"] == "greenhouse"


def freehire_row(**changes):
    return {"public_slug": "acme-engineer", "title": "Engineer", "company": "Acme", "url": "https://example.com/1",
            "location": "Berlin", "posted_at": "2026-09-14", "work_mode": "remote",
            "enrichment": {"employment_type": "full_time"}, **changes}


def test_freehire_endpoint_envelope_encoding_and_pagination():
    calls = []
    provider = FreehireProvider(delay=0, fetch=lambda url, timeout: calls.append(url) or {"data": [freehire_row()], "meta": {"total": 4}})
    result = provider.search(query(keywords="C++ & Python", page=1, limit=1))
    url = urlsplit(calls[0])
    params = parse_qs(url.query)
    assert url.path == "/api/v1/agent/jobs/search"
    assert params["q"] == ["C++ & Python"] and params["offset"] == ["1"]
    assert result.returned == 1 and result.next_page == 2 and result.jobs[0].employment_type == "full_time"


def test_freehire_rejects_ignored_filters_and_impossible_page():
    provider = FreehireProvider(delay=0, fetch=lambda url, timeout: {"data": [], "meta": {"total": 0, "ignored_params": ["work_mode"]}})
    with pytest.raises(ProviderError, match="ignored"):
        provider.search(query())
    with pytest.raises(ProviderError, match="10000"):
        provider.search(query(page=1000, limit=100))


def test_indeed_jobspy_parameters_nan_and_actual_returned():
    calls = []
    class Frame:
        def to_dict(self, mode):
            return [
                {"id": "a", "title": "Engineer", "company": "Acme", "job_url": "https://example.com/1",
                 "job_type": "fulltime", "is_remote": True, "min_amount": 50000, "max_amount": float("nan"), "currency": "EUR"},
                {"title": float("nan"), "company": "Acme", "job_url": "https://example.com/2"},
            ]
    def scrape(**kwargs):
        calls.append(kwargs)
        return Frame()
    provider = IndeedProvider(country="germany", scrape=scrape)
    result = provider.search(query(limit=2, page=1))
    assert result.returned == 1 and result.status == "partial"
    assert result.jobs[0].salary == "EUR 50000"
    assert result.jobs[0].employment_type == "full_time" and result.jobs[0].workplace_type == "remote"
    assert calls[0]["country_indeed"] == "germany" and calls[0]["offset"] == 2
    assert calls[0]["hours_old"] is None and "radius" not in calls[0]
    assert provider.search(query(limit=2, page=1)).cached


def test_indeed_missing_dependency_is_actionable(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "jobspy", None)
    with pytest.raises(ProviderError, match="optional extra") as error:
        IndeedProvider().search(query())
    assert error.value.code == "dependency_missing"


def test_skill_extraction_only_runs_for_the_returned_page(monkeypatch):
    calls = []
    monkeypatch.setattr("ats_matcher.jobs.providers.ats.mentioned_skills", lambda text: calls.append(text) or ["Python"])
    result = greenhouse([posting(n) for n in range(100)]).search(query(limit=2, page=1))
    assert result.returned == 2 and len(calls) == 2
    assert all(job.skills == ["Python"] for job in result.jobs)


@pytest.mark.parametrize("filters", [{"job_type": "full_time"}, {"workplace_type": "remote"}])
def test_greenhouse_reports_unavailable_fields_instead_of_empty_results(filters):
    with pytest.raises(ProviderError) as error:
        greenhouse().search(query(**filters))
    assert error.value.code == "unsupported_filter"
