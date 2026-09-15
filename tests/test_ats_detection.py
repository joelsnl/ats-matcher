from __future__ import annotations

import pytest
from ats_matcher.jobs.ats_detector import ATSDetector
from ats_matcher.jobs.company_registry import CompanyRegistry


class TestATSDetectionIntegration:
    def test_detect_and_lookup_company(self):
        url = "https://boards.greenhouse.io/stripe/jobs"
        detection = ATSDetector.detect(url)
        assert detection is not None
        ats_type, board_slug = detection
        assert ats_type == "greenhouse"
        assert board_slug == "stripe"
        
        registry = CompanyRegistry()
        company = registry.get(board_slug)
        assert company is not None
        assert company.ats_type == ats_type

    def test_detect_various_greenhouse_urls(self):
        urls = [
            "https://boards.greenhouse.io/airbnb",
            "https://airbnb.greenhouse.io/jobs",
            "boards.greenhouse.io/datadog/jobs/123",
        ]
        for url in urls:
            detection = ATSDetector.detect(url)
            assert detection is not None
            ats_type, _ = detection
            assert ats_type == "greenhouse"

    def test_detect_various_lever_urls(self):
        urls = [
            "https://api.lever.co/v0/postings/netflix",
            "https://netflix.lever.co",
            "https://netflix.lever.co/apply/job123",
        ]
        for url in urls:
            detection = ATSDetector.detect(url)
            assert detection is not None
            ats_type, _ = detection
            assert ats_type == "lever"

    def test_detect_various_ashby_urls(self):
        urls = [
            "https://jobs.ashbyhq.com/openai/jobs",
            "https://openai.ashbyhq.com",
        ]
        for url in urls:
            detection = ATSDetector.detect(url)
            assert detection is not None
            ats_type, _ = detection
            assert ats_type == "ashby"

    def test_detect_workday_urls(self):
        urls = [
            "https://microsoft.myworkdayjobs.com/en-US/microsoft/jobs",
            "https://apple.myworkdayjobs.com",
        ]
        for url in urls:
            detection = ATSDetector.detect(url)
            assert detection is not None
            ats_type, board_slug = detection
            assert ats_type == "workday"

    def test_suggest_providers_from_urls(self):
        test_cases = [
            ("https://boards.greenhouse.io/stripe", ["greenhouse"]),
            ("https://netflix.lever.co", ["lever"]),
            ("https://jobs.ashbyhq.com/openai", ["ashby"]),
        ]
        for url, expected_providers in test_cases:
            providers = ATSDetector.suggest_providers(url)
            assert any(p in providers for p in expected_providers)

    def test_registry_covers_detected_ats(self):
        registry = CompanyRegistry()
        detected_ats_types = set()
        for company in registry.list_all():
            detected_ats_types.add(company.ats_type)
        
        test_urls = {
            "greenhouse": "https://boards.greenhouse.io/stripe",
            "lever": "https://netflix.lever.co",
            "ashby": "https://jobs.ashbyhq.com/openai",
            "workday": "https://microsoft.myworkdayjobs.com",
        }
        for ats_type, url in test_urls.items():
            if ats_type in detected_ats_types:
                detection = ATSDetector.detect(url)
                assert detection is not None
                assert detection[0] == ats_type
