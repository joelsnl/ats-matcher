from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class JobSearchQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keywords: str
    location: str | None = None
    f_TPR: str = "r604800"
    f_E: str | None = None
    f_WT: str | None = None


class Job(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    company: str
    location: str | None = None
    posted_at: str | None = None
    posted_relative: str | None = None
    application_url: str
    job_id: str
    source: str = "linkedin"
    employment_type: Literal["full_time", "part_time", "contract", "internship", "temporary"] | None = None
    workplace_type: Literal["on_site", "remote", "hybrid"] | None = None


class JobsMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested: int
    returned: int
    provider: str
    query_used: JobSearchQuery | None = None
    errors: list[str] = Field(default_factory=list)
