from __future__ import annotations

from pathlib import Path

from ats_matcher.config import Settings, get_settings
from ats_matcher.extract.rules import preextract
from ats_matcher.extract.text import ExtractedDocument, extract_document
from ats_matcher.geo import format_search_location
from ats_matcher.jobs.service import JobSearchService
from ats_matcher.jobs.skills import score_job
from ats_matcher.schemas.jobs import JobSearchQuery
from ats_matcher.llm.engine import LlamaEngine
from ats_matcher.llm.merge import hints_to_cv
from ats_matcher.schemas.cv import CvExtract
from ats_matcher.schemas.profile import EnrichedProfile
from ats_matcher.schemas.report import MatchReport


def parse_cv(
    cv_path: str | Path,
    *,
    model_path: str | Path | None = None,
    rules_only: bool = False,
    include_age: bool = False,
    n_ctx: int | None = None,
    n_gpu_layers: int | None = None,
    settings: Settings | None = None,
    engine: LlamaEngine | None = None,
) -> tuple[CvExtract, ExtractedDocument]:
    settings = settings or get_settings()
    document = extract_document(cv_path)
    hints = preextract(document.text)
    if rules_only:
        return hints_to_cv(hints), document

    if engine is None:
        engine = LlamaEngine(
            model_path or settings.llama_model_path,
            n_ctx=n_ctx or settings.llama_n_ctx,
            n_gpu_layers=n_gpu_layers if n_gpu_layers is not None else settings.llama_n_gpu_layers,
        )
    profile = engine.extract(document.text, hints, include_age=include_age)
    return profile, document


def enrich_profile(profile: CvExtract) -> EnrichedProfile:
    raise NotImplementedError("GitHub enrichment is not implemented.")


def match_jobs(
    profile: CvExtract,
    limit: int = 15,
    *,
    keywords: str | None = None,
    location: str | None = None,
    providers: list[str] | None = None,
    source_cv: str = "",
    service: JobSearchService | None = None,
    translate_to: str | None = None,
    translate: bool | None = None,
) -> MatchReport:
    enriched = profile if isinstance(profile, EnrichedProfile) else EnrichedProfile.model_validate(profile.model_dump())
    existing_query = enriched.search_query
    if keywords is None and existing_query is None:
        titles = profile.possible_titles or profile.recent_titles
        if not titles:
            raise ValueError("No job titles were found. Provide --keyword or use a fuller parsed profile.")
        keywords = " OR ".join('"' + title.replace('"', '') + '"' for title in titles[:3])
    values = existing_query.model_dump() if existing_query else {"keywords": keywords}
    if keywords is not None:
        values["keywords"] = keywords
    values["limit"] = limit
    if location is not None:
        values["location"] = location
    elif not values.get("location"):
        values["location"] = format_search_location(profile.location)
    query = JobSearchQuery.model_validate(values)
    enriched = enriched.model_copy(update={"search_query": query})
    result = (service or JobSearchService()).search(query, providers, translate_to=translate_to, translate=translate)
    jobs = [score_job(job, profile.skills) for job in result.jobs]
    jobs.sort(key=lambda job: (len(job.matched_skills), job.match_score or 0), reverse=True)
    return MatchReport(source_cv=source_cv, user_profile=enriched, jobs=jobs, jobs_meta=result.jobs_meta)
