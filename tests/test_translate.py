from __future__ import annotations

import json

from ats_matcher.config import Settings
from ats_matcher.jobs.registry import ProviderRegistry
from ats_matcher.jobs.service import JobSearchService
from ats_matcher.jobs.translate import GoogleTranslator, chunk_text, looks_english, normalize_language, translate_jobs
from ats_matcher.schemas.jobs import Job, JobSearchQuery, ProviderResult


DUTCH = "Wij zoeken een ervaren engineer. Je werkt met Azure en Terraform voor onze klanten in Amsterdam. De functie is hybrid."
ENGLISH = "We are looking for an experienced engineer. You will work with Azure and Terraform for our customers in Amsterdam. The role is hybrid."


def make_job(**extra):
    return Job(job_id="1", title="Engineer", company="Example", application_url="https://www.linkedin.com/jobs/view/1", **extra)


class FakeProvider:
    name = "linkedin"

    def __init__(self, jobs):
        self.jobs = jobs

    def search(self, query, limit=None):
        return ProviderResult(provider=self.name, jobs=self.jobs, returned=len(self.jobs), pages_fetched=1)


def translator_from_map(mapping, source="nl"):
    from urllib.parse import parse_qs, urlsplit
    def request(method, url, **kwargs):
        if "translate-pa" not in url:
            raise AssertionError(url)
        original = parse_qs(urlsplit(url).query).get("query.text", [""])[0]
        return 200, json.dumps({"translation": mapping.get(original, "Translated"), "sourceLanguage": source}), {}
    return GoogleTranslator(request=request)


def test_normalize_and_english_detection():
    assert normalize_language("EN") == "en"
    assert normalize_language("zh") == "zh-CN"
    assert normalize_language("off") is None
    assert looks_english(ENGLISH)
    assert not looks_english(DUTCH)
    assert looks_english("Build services with Python, SQL and Docker.")
    assert chunk_text("a" * 10, 20) == ["a" * 10]
    assert len(chunk_text(("para\n\n" * 40) + "end", 30)) > 1


def test_google_pa_translates_and_records_source_language():
    translator = translator_from_map({DUTCH: ENGLISH})
    result = translator.translate(DUTCH, "en")
    assert result.translated
    assert result.text == ENGLISH
    assert result.source_language == "nl"
    assert result.target_language == "en"
    again = translator.translate(DUTCH, "en")
    assert again.text == ENGLISH


def test_english_descriptions_are_not_sent():
    calls = []
    def request(method, url, **kwargs):
        calls.append(url)
        return 200, "{}", {}
    result = GoogleTranslator(request=request).translate(ENGLISH, "en")
    assert not result.translated
    assert result.text == ENGLISH
    assert calls == []


def test_gtx_is_used_when_pa_fails():
    def request(method, url, **kwargs):
        if "translate-pa" in url:
            return 403, "no", {}
        if "translate_a/single" in url:
            return 200, json.dumps({"sentences": [{"trans": ENGLISH}], "src": "nl"}), {}
        raise AssertionError(url)
    result = GoogleTranslator(request=request).translate(DUTCH, "en")
    assert result.text == ENGLISH
    assert result.source_language == "nl"


def test_search_translates_non_english_listings(monkeypatch):
    translator = translator_from_map({DUTCH: ENGLISH})
    registry = ProviderRegistry()
    registry.register("linkedin", lambda: FakeProvider([make_job(description=DUTCH)]))
    service = JobSearchService(registry, Settings(_env_file=None, jobs_translate=True, jobs_translate_to="en"), translator)
    result = service.search(JobSearchQuery(keywords="engineer", limit=1))
    job = result.jobs[0]
    assert job.description == DUTCH
    assert job.translated_description == ENGLISH
    assert job.source_language == "nl"
    assert job.translation_language == "en"
    assert any("Translated 1 listing" in note for note in result.jobs_meta.warnings)


def test_search_keeps_original_when_translation_is_disabled():
    registry = ProviderRegistry()
    registry.register("linkedin", lambda: FakeProvider([make_job(description=DUTCH)]))
    service = JobSearchService(registry, Settings(_env_file=None, jobs_translate=False), translator_from_map({DUTCH: ENGLISH}))
    result = service.search(JobSearchQuery(keywords="engineer", limit=1), translate=False)
    assert result.jobs[0].translated_description is None
    assert result.jobs[0].description == DUTCH


def test_translate_jobs_keeps_original_after_a_failure():
    def request(method, url, **kwargs):
        raise TimeoutError("offline")
    jobs = translate_jobs([make_job(description=DUTCH)], "en", GoogleTranslator(request=request), [])
    assert jobs[0].description == DUTCH
    assert jobs[0].translated_description is None


def test_skill_overlap_uses_translated_description():
    from ats_matcher.jobs.skills import score_job
    job = make_job(description="Wij zoeken een collega.", translated_description="Build services with Python and Ansible.")
    scored = score_job(job, ["Python", "Ansible", "Figma"])
    assert scored.matched_skills == ["Python", "Ansible"]
