from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from ats_matcher.cli import app
from ats_matcher.config import Settings
from ats_matcher.jobs.base import ProviderError
from ats_matcher.jobs.cache import JobCache
from ats_matcher.jobs.providers.linkedin import LinkedInProvider, build_posting_url, build_search_url, build_view_url, parse_job_cards, parse_job_posting
from ats_matcher.jobs.registry import ProviderRegistry
from ats_matcher.jobs.service import JobSearchService
from ats_matcher.pipeline import match_jobs
from ats_matcher.schemas.cv import CvExtract, Location
from ats_matcher.schemas.jobs import Job, JobSearchQuery, ProviderResult


def card(id=123456, title="Software &amp; Platform Engineer", company="Example Company", extra=""):
    return f'''<li><div class="base-card base-search-card" data-entity-urn="urn:li:jobPosting:{id}">
      <a class="base-card__full-link" href="https://de.linkedin.com/jobs/view/software-engineer-{id}?trackingId=ignore"></a>
      <img class="artdeco-entity-image" data-delayed-url="https://media.licdn.com/logo.png">
      <h3 class="base-search-card__title">{title}</h3>
      <h4 class="base-search-card__subtitle"><a>{company}</a></h4>
      <span class="job-search-card__location"> Berlin, Germany </span>
      <span class="job-search-card__salary-info"> EUR 60,000
        - 80,000 </span>
      <time class="job-search-card__listdate--new" datetime="2026-09-12">1 hour ago</time>{extra}
    </div></li>'''


def provider(fetch, **kwargs):
    kwargs.setdefault("fetch_descriptions", False)
    return LinkedInProvider(fetch=fetch, delay=0, sleep=lambda _: None, **kwargs)


def make_job(id="123456", source="linkedin", url=None):
    return Job(job_id=id, title="Engineer", company="Example", source=source, application_url=url or f"https://www.linkedin.com/jobs/view/{id}")


class FakeProvider:
    def __init__(self, name, jobs=None, error=None):
        self.name, self.jobs, self.error = name, jobs or [], error
        self.queries = []

    def search(self, query, limit=None):
        self.queries.append(query)
        if self.error:
            raise self.error
        return ProviderResult(provider=self.name, jobs=self.jobs, returned=len(self.jobs), pages_fetched=1)


def service(*adapters):
    registry = ProviderRegistry()
    for adapter in adapters:
        registry.register(adapter.name, lambda a=adapter: a)
    return JobSearchService(registry, Settings(_env_file=None, jobs_translate=False))


def test_reference_options_and_url_encoding():
    query = JobSearchQuery(keyword="  software engineer & C++ ", location="New York", dateSincePosted="past Week", jobType="full-time", remoteFilter="on site", experienceLevel="entry level", salary="100000", sortBy="recent", limit="10", page="2", has_verification=True, under_10_applicants=True)
    params = parse_qs(urlsplit(build_search_url(query)).query)
    assert params == {"keywords": ["software engineer & C++"], "location": ["New York"], "f_TPR": ["r604800"], "f_JT": ["F"], "f_WT": ["1"], "f_E": ["2"], "f_SB2": ["4"], "sortBy": ["DD"], "start": ["50"], "f_VJ": ["true"], "f_EA": ["true"]}


@pytest.mark.parametrize("field,values,codes,key", [
    ("date_since_posted", ["past_month", "past_week", "24hr"], ["r2592000", "r604800", "r86400"], "f_TPR"),
    ("job_type", ["full_time", "part_time", "contract", "temporary", "volunteer", "internship"], ["F", "P", "C", "T", "V", "I"], "f_JT"),
    ("workplace_type", ["on_site", "remote", "hybrid"], ["1", "2", "3"], "f_WT"),
    ("experience_level", ["internship", "entry_level", "associate", "senior", "director", "executive"], ["1", "2", "3", "4", "5", "6"], "f_E"),
    ("salary", [40000, 60000, 80000, 100000, 120000], ["1", "2", "3", "4", "5"], "f_SB2"),
])
def test_filter_mapping(field, values, codes, key):
    for value, code in zip(values, codes):
        query = JobSearchQuery(keywords="engineer", **{field: value})
        assert parse_qs(urlsplit(build_search_url(query)).query)[key] == [code]


def test_false_flags_and_any_date_are_omitted():
    params = parse_qs(urlsplit(build_search_url(JobSearchQuery(keywords="engineer", date_since_posted="any"))).query)
    assert not {"f_VJ", "f_EA", "f_TPR"}.intersection(params)


def test_old_profile_filters_migrate():
    query = JobSearchQuery(keywords="engineer", f_TPR="r86400", f_E="4", f_WT="2")
    assert (query.date_since_posted, query.experience_level, query.workplace_type) == ("24hr", "senior", "remote")


@pytest.mark.parametrize("bad", [{"limit": 0}, {"limit": 101}, {"page": -1}, {"salary": 50000}, {"jobType": "anything"}, {"host": "localhost"}, {"f_E": "77"}])
def test_invalid_options_are_rejected(bad):
    with pytest.raises(ValidationError):
        JobSearchQuery(keywords="engineer", **bad)


def test_parse_all_listing_fields_without_inventing_requirements():
    jobs, skipped = parse_job_cards(card())
    assert skipped == 0
    job = jobs[0]
    assert job.title == "Software & Platform Engineer"
    assert job.company == "Example Company"
    assert job.location == "Berlin, Germany"
    assert job.job_id == "123456"
    assert job.salary == "EUR 60,000 - 80,000"
    assert job.posted_at == "2026-09-12"
    assert job.posted_relative == "1 hour ago"
    assert job.company_logo == "https://media.licdn.com/logo.png"
    assert job.application_url == "https://de.linkedin.com/jobs/view/software-engineer-123456"
    assert job.skills == [] and job.description is None
    assert job.workplace_type is None and job.employment_type is None
    assert job.easy_apply is None and job.external_apply_url is None


def test_skip_bad_card_keep_valid_cards():
    jobs, skipped = parse_job_cards(card() + card(999999, title="") + card(888888).replace('https://de.linkedin.com/jobs/view/software-engineer-888888?trackingId=ignore', 'javascript:alert(1)'))
    assert len(jobs) == 1 and skipped == 2


@pytest.mark.parametrize("html,code", [("<html>Sign in <form name=\"session_key\"></form></html>", "access_blocked"), ("<html><p>Something changed</p></html>", "invalid_response"), (card(title=""), "invalid_response")])
def test_bad_response_is_not_empty_success(html, code):
    with pytest.raises(ProviderError) as exc:
        parse_job_cards(html)
    assert exc.value.code == code


def test_empty_search_response():
    assert parse_job_cards(" \n") == ([], 0)
    assert parse_job_cards('<div class="jobs-search-no-results-banner">No matching jobs</div>') == ([], 0)


def test_pagination_limit_and_duplicates():
    offsets = []
    def fetch(url, timeout):
        offset = int(parse_qs(urlsplit(url).query)["start"][0])
        offsets.append(offset)
        return {25: card(1) + card(1) + card(2), 50: card(2) + card(3) + card(4)}[offset]
    result = provider(fetch).search(JobSearchQuery(keywords="engineer", page=1, limit=3))
    assert offsets == [25, 50]
    assert [j.job_id for j in result.jobs] == ["1", "2", "3"]
    assert result.next_page == 3


def test_second_page_failure_preserves_results_and_is_not_cached():
    calls = []
    def fetch(url, timeout):
        calls.append(url)
        if parse_qs(urlsplit(url).query)["start"] == ["0"]:
            return card()
        raise ProviderError("rate_limited", "Wait before retrying.", 60)
    now = [0]
    p = provider(fetch, clock=lambda: now[0])
    query = JobSearchQuery(keywords="engineer", limit=2)
    result = p.search(query)
    assert result.status == "partial" and result.returned == 1
    assert result.error_code == "rate_limited" and result.retry_after == 60
    assert result.next_page == 1
    assert p.search(query).retry_after == 60
    assert len(calls) == 2
    now[0] = 60
    p.search(query)
    assert len(calls) == 4


def test_repeated_page_stops_and_warns():
    calls = []
    p = provider(lambda url, timeout: calls.append(url) or card())
    result = p.search(JobSearchQuery(keywords="engineer", limit=100))
    assert len(calls) == 2 and result.status == "partial"
    assert "repeated" in result.warnings[0]


def test_request_retries_transient_failures_only():
    calls = []
    def fetch(url, timeout):
        calls.append(url)
        if len(calls) < 3:
            raise ProviderError("temporarily_unavailable", "Unavailable")
        return card()
    assert provider(fetch).search(JobSearchQuery(keywords="engineer", limit=1)).status == "ok"
    assert len(calls) == 3
    calls.clear()
    def blocked(url, timeout):
        calls.append(url)
        raise ProviderError("access_blocked", "Blocked")
    assert provider(blocked).search(JobSearchQuery(keywords="engineer")).status == "error"
    assert len(calls) == 1


def test_cache_separates_page_and_limit_and_returns_copies():
    now = [10]
    cache = JobCache(ttl=5, max_entries=1, clock=lambda: now[0])
    original = ProviderResult(provider="linkedin", jobs=[make_job()], returned=1)
    cache.set("a", original)
    got = cache.get("a")
    got.jobs[0].title = "Changed"
    assert cache.get("a").jobs[0].title == "Engineer"
    now[0] = 15
    assert cache.get("a") is None
    cache.set("a", original)
    cache.set("b", original)
    assert cache.get("a") is None
    calls = []
    p = provider(lambda url, timeout: calls.append(url) or card())
    q = JobSearchQuery(keywords="engineer", limit=1)
    assert not p.search(q).cached
    assert p.search(q).cached
    p.search(q.model_copy(update={"page": 1}))
    assert len(calls) == 2
    p.search(q.model_copy(update={"limit": 2}))
    assert len(calls) == 4


def test_multiple_channels_keep_successes_and_deduplicate():
    first = FakeProvider("first", [make_job(source="first")])
    duplicate = FakeProvider("second", [make_job(source="second"), make_job(id="999", source="second")])
    failed = FakeProvider("third", error=ProviderError("rate_limited", "Wait"))
    result = service(first, duplicate, failed).search(JobSearchQuery(keywords="engineer"), ["first", "second", "third"])
    assert len(result.jobs) == 2
    assert result.jobs_meta.status == "partial"
    assert len(result.jobs_meta.providers) == 3
    assert result.jobs_meta.errors == ["third: Wait"]


def test_unknown_source_fails_before_network():
    fake = FakeProvider("known")
    with pytest.raises(ValueError, match="Unknown job provider"):
        service(fake).search(JobSearchQuery(keywords="engineer"), ["known", "unknown"])
    assert not fake.queries


def test_profile_search_uses_titles_and_excludes_contact_details():
    fake = FakeProvider("linkedin", [make_job()])
    profile = CvExtract(full_name="Private Person", email="private@example.com", possible_titles=["Backend Engineer", "Platform Engineer"], location=Location(city="Berlin"))
    report = match_jobs(profile, service=service(fake))
    assert fake.queries[0].keywords == '"Backend Engineer" OR "Platform Engineer"'
    assert fake.queries[0].location == "Berlin, Germany"
    assert "Private Person" not in fake.queries[0].model_dump_json()
    assert len(report.jobs) == 1
    with pytest.raises(ValueError, match="--keyword"):
        match_jobs(CvExtract(), service=service(fake))


def test_cli_direct_search_and_profile_run(monkeypatch, tmp_path):
    fake = FakeProvider("linkedin", [make_job()])
    search_service = service(fake)
    monkeypatch.setattr("ats_matcher.cli.JobSearchService", lambda: search_service)
    monkeypatch.setattr("ats_matcher.pipeline.JobSearchService", lambda: search_service)
    runner = CliRunner()
    result = runner.invoke(app, ["search", "--keyword", "engineer", "--workplace", "remote", "--limit", "1"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["jobs"][0]["job_id"] == "123456"
    assert fake.queries[0].workplace_type == "remote"
    cv = tmp_path / "cv.txt"
    cv.write_text("Taylor Example taylor@example.com")
    out = tmp_path / "report.json"
    result = runner.invoke(app, ["run", "--cv", str(cv), "--rules-only", "--keyword", "engineer", "--out", str(out)])
    assert result.exit_code == 0, result.output
    payload = json.loads(out.read_text())
    assert len(payload["jobs"]) == 1 and "birth_year" not in payload["user_profile"]


def test_cli_failed_provider_is_nonzero_and_structured(monkeypatch):
    fake = FakeProvider("linkedin", error=ProviderError("rate_limited", "Wait"))
    monkeypatch.setattr("ats_matcher.cli.JobSearchService", lambda: service(fake))
    result = CliRunner().invoke(app, ["search", "--keyword", "engineer"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["jobs_meta"]["providers"][0]["error_code"] == "rate_limited"


# Regressions from the upstream issue review; see docs/upstream-issue-review.md.
def test_multiple_filters_accept_arrays_aliases_and_cli_commas():
    q = JobSearchQuery(keyword="engineer", jobType=["part time", "internship", "part-time"], remoteFilter="on site, hybrid", experienceLevel=["entry level", "associate"])
    params = parse_qs(urlsplit(build_search_url(q)).query)
    assert set(params["f_JT"][0].split(",")) == {"P", "I"}
    assert set(params["f_WT"][0].split(",")) == {"1", "3"}
    assert set(params["f_E"][0].split(",")) == {"2", "3"}
    assert q.job_type == ["internship", "part_time"]


@pytest.mark.parametrize("bad", [
    {"jobType": []}, {"jobType": ["contract", "unknown"]},
    {"remoteFilter": ["remote", None]}, {"remoteFilter": "remote,"},
    {"experienceLevel": [""]}, {"jobType": [["contract"]]}, {"remoteFilter": ["remote", "-"]},
    {"posted_within_days": 0}, {"posted_within_days": 366},
    {"posted_within_days": 2.5}, {"posted_within_days": True},
    {"dateSincePosted": "last Tuesday"}, {"f_E": []},
])
def test_extended_filters_reject_invalid_values(bad):
    with pytest.raises(ValidationError):
        JobSearchQuery(keywords="engineer", **bad)


@pytest.mark.parametrize("days", [1, 3, 365])
def test_custom_days_override_date_preset(days):
    q = JobSearchQuery(keyword="engineer", postedWithinDays=days, dateSincePosted="past month")
    assert parse_qs(urlsplit(build_search_url(q)).query)["f_TPR"] == [f"r{days * 86400}"]


def test_24h_issue_payload_keeps_date_filter():
    q = JobSearchQuery(keyword="python developer", location="India", dateSincePosted="24h", jobType="contract", remoteFilter="remote", salary="100000", experienceLevel="senior", limit="15", page="0", sortBy="recent")
    assert q.date_since_posted == "24hr"
    assert parse_qs(urlsplit(build_search_url(q)).query)["f_TPR"] == ["r86400"]


@pytest.mark.parametrize("attrs,expected", [
    ('src="https://media.licdn.com/real.png"', "https://media.licdn.com/real.png"),
    ('src="data:image/gif;base64,placeholder" data-delayed-url="https://media.licdn.com/real.png"', "https://media.licdn.com/real.png"),
    ('data-delayed-url="https://[broken" src="https://media.licdn.com/real.png"', "https://media.licdn.com/real.png"),
    ('src="https://[broken"', None),
])
def test_logo_variations_do_not_discard_valid_jobs(attrs, expected):
    html = card().replace('data-delayed-url="https://media.licdn.com/logo.png"', attrs)
    jobs, skipped = parse_job_cards(html)
    assert len(jobs) == 1 and skipped == 0
    assert jobs[0].company_logo == expected


def test_malformed_listing_url_does_not_discard_other_jobs():
    bad = card(2).replace("https://de.linkedin.com/jobs/view/software-engineer-2?trackingId=ignore", "https://[broken")
    jobs, skipped = parse_job_cards(card(1) + bad)
    assert [j.job_id for j in jobs] == ["1"] and skipped == 1


def test_larger_limit_fetches_more_and_filter_cache_keys_are_independent():
    calls = []
    p = provider(lambda url, timeout: calls.append(url) or card(1) + card(2) + card(3))
    q = JobSearchQuery(keywords="engineer", limit=1)
    assert p.search(q).returned == 1
    larger = q.model_copy(update={"limit": 3})
    assert p.search(larger).returned == 3
    assert len(calls) == 2
    assert p.search(larger).cached
    multi = JobSearchQuery(keywords="engineer", limit=1, remoteFilter=["remote", "hybrid"], postedWithinDays=3)
    assert not p.search(multi).cached
    equivalent = JobSearchQuery(keywords="engineer", limit=1, remoteFilter=["hybrid", "remote", "remote"], postedWithinDays=3)
    assert p.search(equivalent).cached
    assert not p.search(multi.model_copy(update={"posted_within_days": 4})).cached
    assert not p.search(multi.model_copy(update={"workplace_type": "remote"})).cached


def test_retry_after_accepts_seconds_and_http_dates():
    from datetime import datetime, timezone
    from ats_matcher.jobs.providers.linkedin import retry_after_seconds
    now = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
    assert retry_after_seconds("120", now) == 120
    assert retry_after_seconds("Sat, 12 Sep 2026 12:02:00 GMT", now) == 120
    assert retry_after_seconds("Sat, 12 Sep 2026 11:59:00 GMT", now) == 0
    assert retry_after_seconds("nonsense", now) is None


@pytest.mark.parametrize("status,code", [(429, "rate_limited"), (302, "access_blocked"), (403, "access_blocked"), (999, "access_blocked"), (503, "temporarily_unavailable"), (404, "http_error")])
def test_http_failures_are_classified(monkeypatch, status, code):
    from email.message import Message
    from urllib.error import HTTPError
    from ats_matcher.jobs.providers.linkedin import fetch_html
    headers = Message()
    headers["Retry-After"] = "120"
    class Opener:
        def open(self, request, timeout):
            raise HTTPError(request.full_url, status, "upstream error", headers, None)
    monkeypatch.setattr("ats_matcher.jobs.providers.linkedin.build_opener", lambda *args: Opener())
    with pytest.raises(ProviderError) as exc:
        fetch_html(build_search_url(JobSearchQuery(keywords="engineer")), 15)
    assert exc.value.code == code
    if status == 429:
        assert exc.value.retry_after == 120


@pytest.mark.parametrize("retry_after,expected", [(None, 60), (120, 120), (0, 1)])
def test_rate_limit_cooldown_applies_across_queries_and_expires(retry_after, expected):
    now, calls = [0], []
    def fetch(url, timeout):
        calls.append(url)
        if len(calls) == 2:
            raise ProviderError("rate_limited", "Wait", retry_after)
        return card()
    p = provider(fetch, clock=lambda: now[0])
    cached_query = JobSearchQuery(keywords="cached", limit=1)
    assert p.search(cached_query).status == "ok"
    q = JobSearchQuery(keywords="engineer", limit=1)
    assert p.search(q).retry_after == expected
    other = p.search(JobSearchQuery(keywords="designer"))
    assert other.error_code == "rate_limited" and other.pages_fetched == 0
    assert len(calls) == 2
    assert p.search(cached_query).cached
    now[0] = expected
    assert p.search(q).status == "ok"
    assert len(calls) == 3


def test_cli_multiple_filters_and_custom_days(monkeypatch):
    fake = FakeProvider("linkedin", [make_job()])
    monkeypatch.setattr("ats_matcher.cli.JobSearchService", lambda: service(fake))
    result = CliRunner().invoke(app, ["search", "--keyword", "engineer", "--job-type", "part_time,internship", "--workplace", "remote,hybrid", "--experience", "entry_level,associate", "--days", "3"])
    assert result.exit_code == 0, result.output
    q = fake.queries[0]
    assert set(q.job_type) == {"part_time", "internship"}
    assert set(q.workplace_type) == {"remote", "hybrid"}
    assert set(q.experience_level) == {"entry_level", "associate"}
    assert q.posted_within_days == 3


POSTING_HTML = '''
<section class="core-section-container my-3 description">
  <div class="description__text description__text--rich">
    <section class="show-more-less-html">
      <div class="show-more-less-html__markup show-more-less-html__markup--clamp-after-5 relative overflow-hidden">
        <strong>About the role</strong>
        <p>Build services with Python, SQL and Docker.</p>
        <ul><li>Work with React and TypeScript</li></ul>
        <p>Also listed later in the same markup: Kubernetes.</p>
      </div>
      <button class="show-more-less-html__button show-more-less-html__button--more">Show more</button>
      <button class="show-more-less-html__button show-more-less-html__button--less">Show less</button>
    </section>
  </div>
  <ul class="description__job-criteria-list">
    <li class="description__job-criteria-item">
      <h3 class="description__job-criteria-subheader">Seniority level</h3>
      <span class="description__job-criteria-text">Mid-Senior level</span>
    </li>
    <li class="description__job-criteria-item">
      <h3 class="description__job-criteria-subheader">Employment type</h3>
      <span class="description__job-criteria-text">Full-time</span>
    </li>
    <li class="description__job-criteria-item">
      <h3 class="description__job-criteria-subheader">Workplace type</h3>
      <span class="description__job-criteria-text">Hybrid</span>
    </li>
  </ul>
</section>
<form name="session_key"></form>
'''


def test_parse_posting_reads_full_clamped_description():
    details = parse_job_posting(POSTING_HTML)
    assert "Kubernetes" in details["description"]
    assert "Python" in details["description"]
    assert "• Work with React and TypeScript" in details["description"]
    assert "Show more" not in details["description"]
    assert details["employment_type"] == "full_time"
    assert details["workplace_type"] == "hybrid"
    assert {"Python", "SQL", "Docker", "React", "TypeScript", "Kubernetes"} <= set(details["skills"])


SDUI_HTML = '''
<div data-sdui-component="com.linkedin.sdui.generated.jobseeker.dsl.impl.aboutTheJob">
  <div class="hashed-wrapper-one hashed-wrapper-two">
    <h2>About the job</h2>
    <p>
      <span tabindex="-1" data-testid="expandable-text-box">
        <p><strong>Platform Engineer</strong></p>
        <p>Build services with Python, SQL and Docker.</p>
        <ul><li>Work with React and TypeScript</li></ul>
        <p>Also listed later in the same markup: Kubernetes.</p>
      </span>
    </p>
  </div>
</div>
'''


def test_parse_sdui_about_the_job_description():
    details = parse_job_posting(SDUI_HTML)
    assert "Kubernetes" in details["description"]
    assert "Python" in details["description"]
    assert "• Work with React and TypeScript" in details["description"]
    assert "About the job" not in details["description"]
    assert {"Python", "SQL", "Docker", "React", "TypeScript", "Kubernetes"} <= set(details["skills"])


def test_parse_expandable_text_box_without_sdui_wrapper():
    html = '<span data-testid="expandable-text-box"><p>Build services with Python, SQL and Docker. Kubernetes is listed too.</p></span>'
    details = parse_job_posting(html)
    assert "Kubernetes" in details["description"]
    assert "Python" in details["description"]


def test_parse_easy_apply_from_search_card():
    jobs, _ = parse_job_cards(card(extra='<span class="job-search-card__easy-apply-label">Easy Apply</span>'))
    assert jobs[0].easy_apply is True
    assert jobs[0].external_apply_url is None
    dutch, _ = parse_job_cards(card(id=2, extra='<span class="result-benefits__text">Eenvoudig solliciteren</span>'))
    assert dutch[0].easy_apply is True


def test_parse_company_apply_url_from_hidden_code():
    html = POSTING_HTML + '<code id="applyUrl"><!--https://www.linkedin.com/jobs/apply-with-linkedin?url=https%3A%2F%2Fboards.greenhouse.io%2Fexample%2Fjobs%2F99--></code>'
    details = parse_job_posting(html)
    assert details["easy_apply"] is False
    assert details["external_apply_url"] == "https://boards.greenhouse.io/example/jobs/99"


def test_parse_direct_company_apply_url_and_offsite_button():
    html = POSTING_HTML + '<a class="apply-button" data-tracking-control-name="public_jobs_apply-link-offsite" href="https://www.linkedin.com/signup">Apply</a><code id="applyUrl"><!--https://careers.example.com/jobs/cloud-engineer--></code>'
    details = parse_job_posting(html)
    assert details["easy_apply"] is False
    assert details["external_apply_url"] == "https://careers.example.com/jobs/cloud-engineer"


def test_parse_easy_apply_from_json_ld_and_tracking():
    ld = parse_job_posting('<script type="application/ld+json">{"@type":"JobPosting","description":"<p>Build services with Python, SQL and Docker.</p>","directApply":true}</script>')
    assert ld["easy_apply"] is True
    assert "external_apply_url" not in ld
    tracking = parse_job_posting(POSTING_HTML + '<button class="apply-button" data-tracking-control-name="public_jobs_apply-link-easy_apply">Easy Apply</button>')
    assert tracking["easy_apply"] is True
    assert "external_apply_url" not in tracking


def test_linkedin_apply_urls_are_not_treated_as_company_sites():
    details = parse_job_posting(POSTING_HTML + '<code id="applyUrl"><!--https://www.linkedin.com/jobs/view/123456--></code>')
    assert "external_apply_url" not in details
    job = Job(job_id="1", title="Engineer", company="Example", application_url="https://www.linkedin.com/jobs/view/1", external_apply_url="https://www.linkedin.com/jobs/apply/1")
    assert job.external_apply_url is None


def test_search_copies_company_apply_from_posting_page():
    html = POSTING_HTML + '<code id="applyUrl"><!--https://jobs.example.com/apply/42--></code>'
    def fetch(url, timeout):
        if "jobPosting" in url:
            return html
        return card(extra='<span class="job-search-card__easy-apply-label">Easy Apply</span>')
    result = provider(fetch, fetch_descriptions=True).search(JobSearchQuery(keywords="engineer", limit=1))
    job = result.jobs[0]
    assert job.easy_apply is False
    assert job.external_apply_url == "https://jobs.example.com/apply/42"
    assert "Kubernetes" in job.description
    html = '<script type="application/ld+json">{"@type":"JobPosting","description":"<p>Build services with Python, SQL and Docker. Kubernetes is listed too.</p>","employmentType":["FULL_TIME"],"jobLocationType":"TELECOMMUTE"}</script>'
    details = parse_job_posting(html)
    assert "Kubernetes" in details["description"]
    assert "Python" in details["description"]
    assert details["employment_type"] == "full_time"
    assert details["workplace_type"] == "remote"


def test_parse_sdui_insight_chips_without_using_description_text():
    html = '''
<div data-sdui-component="com.linkedin.sdui.generated.jobseeker.dsl.impl.jobInsight">Full-time · Hybrid</div>
<div data-sdui-component="com.linkedin.sdui.generated.jobseeker.dsl.impl.aboutTheJob">
  <span data-testid="expandable-text-box"><p>Build services with Python, SQL and Docker. Kubernetes is listed too. This mention of remote work is not a workplace chip.</p></span>
</div>
'''
    details = parse_job_posting(html)
    assert details["employment_type"] == "full_time"
    assert details["workplace_type"] == "hybrid"
    assert "Kubernetes" in details["description"]


def test_search_falls_back_to_public_view_page():
    urls = []
    def fetch(url, timeout):
        urls.append(url)
        if "jobPosting" in url:
            return "<html><body>no description here</body></html>"
        if "/jobs/view/" in url:
            assert url == build_view_url("123456")
            return POSTING_HTML
        return card()
    result = provider(fetch, fetch_descriptions=True).search(JobSearchQuery(keywords="engineer", limit=1))
    assert any("jobPosting" in url for url in urls)
    assert any("/jobs/view/" in url for url in urls)
    assert "Kubernetes" in result.jobs[0].description


def test_search_enriches_public_posting_pages():
    def fetch(url, timeout):
        if "jobPosting" in url:
            assert url == build_posting_url("123456")
            return POSTING_HTML
        return card()
    result = provider(fetch, fetch_descriptions=True).search(JobSearchQuery(keywords="engineer", limit=1))
    job = result.jobs[0]
    assert job.description and "Kubernetes" in job.description
    assert job.employment_type == "full_time"
    assert job.workplace_type == "hybrid"
    assert "Python" in job.skills


def test_description_rate_limit_keeps_search_results():
    def fetch(url, timeout):
        if "jobPosting" in url:
            raise ProviderError("rate_limited", "Wait", 60)
        return card(1) + card(2)
    result = provider(fetch, fetch_descriptions=True).search(JobSearchQuery(keywords="engineer", limit=2))
    assert [job.job_id for job in result.jobs] == ["1", "2"]
    assert result.status == "partial"
    assert result.jobs[0].description is None
    assert "descriptions" in " ".join(result.warnings)


def test_match_jobs_orders_by_shared_description_skills():
    low = make_job("1").model_copy(update={"title": "Support", "description": "A customer service role."})
    high = make_job("2").model_copy(update={"title": "Data Engineer", "description": "We need Python, SQL and Docker."})
    fake = FakeProvider("linkedin", [low, high])
    profile = CvExtract(full_name="A", possible_titles=["Engineer"], skills=["Python", "SQL", "Docker"])
    report = match_jobs(profile, service=service(fake))
    assert [job.job_id for job in report.jobs] == ["2", "1"]
    assert set(report.jobs[0].matched_skills) == {"Python", "SQL", "Docker"}
    assert report.jobs[0].match_score == 1.0
