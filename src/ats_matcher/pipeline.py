from __future__ import annotations

from pathlib import Path

from ats_matcher.config import Settings, get_settings
from ats_matcher.extract.rules import preextract
from ats_matcher.extract.text import ExtractedDocument, extract_document
from ats_matcher.jobs.base import NotImplementedProvider
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
    raise NotImplementedError("GitHub enrichment is Phase 3.")


def match_jobs(profile: EnrichedProfile, limit: int = 15) -> MatchReport:
    provider = NotImplementedProvider()
    provider.search(query=profile.search_query, limit=limit)  # type: ignore[arg-type]
    raise NotImplementedError("Job matching is Phase 5.")
