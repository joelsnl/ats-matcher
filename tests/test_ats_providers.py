from __future__ import annotations

import pytest
from ats_matcher.jobs.providers.ats import ATSProvider, make_job
from ats_matcher.jobs.providers.greenhouse import GreenhouseProvider
from ats_matcher.jobs.providers.lever import LeverProvider
from ats_matcher.jobs.providers.ashby import AshbyProvider
from ats_matcher.jobs.ats_detector import ATSDetector
from ats_matcher.jobs.company_registry import CompanyRegistry
from ats_matcher.schemas.jobs import Job, JobSearchQuery


class TestMakeJob:
    def test_make_job_valid(self):
        job = make_job(
            title="Engineer",
            company="Acme",
            location="San Francisco",
            url="https://example.com/jobs/1",
            job_id="1",
            source="test",
        )
        assert job is not None
        assert job.title == "Engineer"
        assert job.company == "Acme"
        assert job.source == "test"

    def test_make_job_strips_whitespace(self):
        job = make_job(
            title="  Engineer  ",
            company="\nAcme\n",
            location="  San Francisco  ",
            url="https://example.com/jobs/1",
            job_id="  1  ",
            source="test",
        )
        assert job.title == "Engineer"
        assert job.company == "Acme"
        assert job.location == "San Francisco"

    def test_make_job_rejects_invalid_url(self):
        assert make_job(
            title="Engineer", company="Acme", location=None,
            url="not-a-url", job_id="1", source="test",
        ) is None

    def test_make_job_rejects_missing_title(self):
        assert make_job(
            title="", company="Acme", location=None,
            url="https://example.com/jobs/1", job_id="1", source="test",
        ) is None

    def test_make_job_rejects_missing_company(self):
        assert make_job(
            title="Engineer", company="", location=None,
            url="https://example.com/jobs/1", job_id="1", source="test",
        ) is None

    def test_make_job_truncates_long_description(self):
        long_desc = "x" * 25000
        job = make_job(
            title="Engineer", company="Acme", location=None,
            url="https://example.com/jobs/1", job_id="1", source="test",
            description=long_desc,
        )
        assert job is not None
        assert len(job.description or "") <= 20000


class TestATSDetector:
    @pytest.mark.parametrize("url,expected_ats,expected_slug", [
        ("https://boards.greenhouse.io/stripe", "greenhouse", "stripe"),
        ("https://boards.greenhouse.io/stripe/jobs/123", "greenhouse", "stripe"),
        ("https://stripe.greenhouse.io/jobs", "greenhouse", "stripe"),
        ("https://api.lever.co/v0/postings/netflix", "lever", "netflix"),
        ("https://netflix.lever.co/apply", "lever", "netflix"),
        ("https://jobs.ashbyhq.com/openai/jobs", "ashby", "openai"),
        ("https://openai.ashbyhq.com", "ashby", "openai"),
        ("https://stripe.myworkdayjobs.com/en-US/stripe/jobs", "workday", "stripe"),
        ("https://jobs.smartrecruiters.com/netflix/search", "smartrecruiters", "netflix"),
        ("https://netflix.teamtailor.com/jobs", "teamtailor", "netflix"),
        ("https://netflix.recruitee.com/api/offers", "recruitee", "netflix"),
    ])
    def test_detect_ats_from_url(self, url, expected_ats, expected_slug):
        result = ATSDetector.detect(url)
        assert result is not None
        ats_type, board_slug = result
        assert ats_type == expected_ats
        assert board_slug == expected_slug

    def test_detect_ats_invalid_url(self):
        assert ATSDetector.detect("not-a-url") is None
        assert ATSDetector.detect("") is None
        assert ATSDetector.detect(None) is None

    def test_suggest_providers_from_url(self):
        providers = ATSDetector.suggest_providers("https://boards.greenhouse.io/stripe")
        assert "greenhouse" in providers


class TestCompanyRegistry:
    def test_registry_loads_companies(self):
        registry = CompanyRegistry()
        assert len(registry.list_all()) > 0

    def test_registry_search_by_name(self):
        registry = CompanyRegistry()
        results = registry.search("stripe")
        assert len(results) > 0
        assert any(c.name.lower() == "stripe" for c in results)

    def test_registry_search_by_slug(self):
        registry = CompanyRegistry()
        results = registry.search("stripe")
        assert len(results) > 0

    def test_registry_get_by_slug(self):
        registry = CompanyRegistry()
        company = registry.get("stripe")
        assert company is not None
        assert company.name == "Stripe"
        assert company.ats_type == "greenhouse"

    def test_registry_list_by_ats(self):
        registry = CompanyRegistry()
        companies = registry.list_by_ats("greenhouse")
        assert len(companies) > 0
        assert all(c.ats_type == "greenhouse" for c in companies)

    def test_registry_search_substring(self):
        registry = CompanyRegistry()
        results = registry.search("spot")
        assert any("spotify" in c.name.lower() for c in results)


class TestGreenhouseProvider:
    def test_provider_name(self):
        provider = GreenhouseProvider()
        assert provider.name == "greenhouse"

    def test_provider_has_boards(self):
        provider = GreenhouseProvider()
        assert len(provider.boards) > 0
        assert "stripe" in provider.boards

    def test_provider_endpoint_format(self):
        provider = GreenhouseProvider()
        url = provider._url("stripe")
        assert "stripe" in url
        assert "boards-api.greenhouse.io" in url

    def test_parse_greenhouse_records(self):
        provider = GreenhouseProvider()
        payload = {
            "jobs": [
                {
                    "id": 123,
                    "title": "Software Engineer",
                    "absolute_url": "https://boards.greenhouse.io/stripe/jobs/123",
                    "location": {"name": "San Francisco, CA"},
                    "updated_at": "2026-01-15",
                }
            ]
        }
        records = provider._records(payload)
        assert len(records) == 1
        assert records[0]["id"] == 123

    def test_convert_greenhouse_job(self):
        provider = GreenhouseProvider()
        record = {
            "id": 123,
            "title": "Software Engineer",
            "absolute_url": "https://boards.greenhouse.io/stripe/jobs/123",
            "location": {"name": "San Francisco, CA"},
            "updated_at": "2026-01-15",
            "content": "Build payment systems",
        }
        job = provider._job(record, "stripe")
        assert job is not None
        assert job.title == "Software Engineer"
        assert job.company == "Stripe"
        assert job.source == "greenhouse"
        assert "stripe" in job.job_id.lower()


class TestLeverProvider:
    def test_provider_name(self):
        provider = LeverProvider()
        assert provider.name == "lever"

    def test_provider_has_boards(self):
        provider = LeverProvider()
        assert "spotify" in provider.boards

    def test_parse_lever_records(self):
        provider = LeverProvider()
        payload = [
            {
                "id": "abc123",
                "text": "Backend Engineer",
                "hostedUrl": "https://netflix.lever.co/apply/abc123",
                "workplaceType": "Remote",
                "descriptionPlain": "Work on backend systems",
            }
        ]
        records = provider._records(payload)
        assert len(records) == 1

    def test_convert_lever_job(self):
        provider = LeverProvider()
        record = {
            "id": "abc123",
            "text": "Backend Engineer",
            "hostedUrl": "https://netflix.lever.co/apply/abc123",
            "workplaceType": "Remote",
            "descriptionPlain": "Work on backend systems",
            "categories": {"location": "San Francisco, CA"},
        }
        job = provider._job(record, "netflix")
        assert job is not None
        assert job.title == "Backend Engineer"
        assert job.workplace_type == "remote"


class TestAshbyProvider:
    def test_provider_name(self):
        provider = AshbyProvider()
        assert provider.name == "ashby"

    def test_provider_has_boards(self):
        provider = AshbyProvider()
        assert "openai" in provider.boards

    def test_parse_ashby_records(self):
        provider = AshbyProvider()
        payload = {
            "jobs": [
                {
                    "jobUrl": "https://jobs.ashbyhq.com/openai/job/123",
                    "title": "ML Engineer",
                    "location": "San Francisco",
                    "workplaceType": "On-site",
                }
            ]
        }
        records = provider._records(payload)
        assert len(records) == 1

    def test_convert_ashby_job(self):
        provider = AshbyProvider()
        record = {
            "jobUrl": "https://jobs.ashbyhq.com/openai/job/123",
            "title": "ML Engineer",
            "location": "San Francisco",
            "workplaceType": "On-site",
            "descriptionPlain": "Build ML systems",
            "publishedAt": "2026-01-15T10:00:00Z",
        }
        job = provider._job(record, "openai")
        assert job is not None
        assert job.title == "ML Engineer"
        assert job.workplace_type == "on_site"
