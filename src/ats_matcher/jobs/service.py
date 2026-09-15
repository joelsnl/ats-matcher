from __future__ import annotations
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from ats_matcher.config import Settings, get_settings
from ats_matcher.jobs.base import ProviderError
from ats_matcher.jobs.ats_detector import ATSDetector, SEARCHABLE_ATS
from ats_matcher.jobs.registry import ProviderRegistry, default_registry
from ats_matcher.jobs.translate import GoogleTranslator, normalize_language, translate_jobs
from ats_matcher.schemas.jobs import JobSearchQuery, JobSearchResponse, JobsMeta, ProviderResult, ProviderStatus


def canonical_url(url: str) -> str:
    p = urlsplit(url)
    tracking = {"trk", "trackingid", "refid", "position", "pagenum"}
    query = sorted((k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith("utm_") and k.lower() not in tracking)
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), urlencode(query), ""))


class JobSearchService:
    def __init__(self, registry: ProviderRegistry | None = None, settings: Settings | None = None, translator: GoogleTranslator | None = None):
        self.settings = settings or get_settings()
        self.registry = registry or default_registry(self.settings)
        self.translator = translator if translator is not None else GoogleTranslator(timeout=self.settings.jobs_timeout)

    def search(self, query: JobSearchQuery, providers: list[str] | None = None, *, translate_to: str | None = None, translate: bool | None = None) -> JobSearchResponse:
        if query.career_url:
            detected = ATSDetector.detect(query.career_url)
            if not detected or detected[0] not in SEARCHABLE_ATS:
                raise ValueError("Use a hosted Greenhouse, Lever, or Ashby career URL.")
            if providers is None:
                providers = [detected[0]]
            elif {name.strip().lower() for name in providers} != {detected[0]}:
                raise ValueError("The career URL must match the selected source.")
        names = list(dict.fromkeys(name.strip().lower() for name in (providers if providers is not None else self.settings.jobs_provider.split(",")) if name.strip()))
        if not names:
            raise ValueError("Select at least one job provider.")
        adapters = [(name, self.registry.get(name)) for name in names]
        jobs, statuses, seen_ids, seen_urls = [], [], set(), set()
        for name, adapter in adapters:
            try:
                result = adapter.search(query)
            except ProviderError as exc:
                result = ProviderResult(provider=name, status="error", error_code=exc.code, error=str(exc), retry_after=exc.retry_after)
            except Exception:
                result = ProviderResult(provider=name, status="error", error_code="provider_error", error="The job provider failed unexpectedly.")
            statuses.append(ProviderStatus.model_validate(result.model_dump(exclude={"jobs"})))
            for job in result.jobs:
                identity, url = (job.source, job.job_id), canonical_url(job.application_url)
                if identity not in seen_ids and url not in seen_urls:
                    jobs.append(job)
                    seen_ids.add(identity)
                    seen_urls.add(url)
        jobs = jobs[:query.limit]
        warnings = [f"{s.provider}: {w}" for s in statuses for w in s.warnings]
        enabled = self.settings.jobs_translate if translate is None else translate
        target = normalize_language(translate_to if translate_to is not None else self.settings.jobs_translate_to)
        if enabled and target and jobs:
            jobs = translate_jobs(jobs, target, self.translator, warnings)
        status = "error" if all(s.status == "error" for s in statuses) else "partial" if any(s.status != "ok" for s in statuses) or any("Could not translate" in note for note in warnings) else "ok"
        return JobSearchResponse(jobs=jobs, jobs_meta=JobsMeta(requested=query.limit, returned=len(jobs), provider=",".join(names), query_used=query, status=status, providers=statuses, errors=[f"{s.provider}: {s.error}" for s in statuses if s.error], warnings=warnings))
