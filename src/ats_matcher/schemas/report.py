from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from ats_matcher.schemas.jobs import Job, JobsMeta
from ats_matcher.schemas.profile import EnrichedProfile


class MatchReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    )
    source_cv: str
    user_profile: EnrichedProfile
    jobs: list[Job] = Field(default_factory=list)
    jobs_meta: JobsMeta
