from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ats_matcher.schemas.cv import CvExtract
from ats_matcher.schemas.jobs import JobSearchQuery


class LanguageShare(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    share: float = Field(ge=0, le=1)


class RepoSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    url: str
    description: str | None = None
    language: str | None = None
    stars: int = 0
    topics: list[str] = Field(default_factory=list)
    updated_at: str | None = None


class GitHubProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str | None = None
    profile_url: str | None = None
    bio: str | None = None
    location: str | None = None
    public_repos: int = 0
    top_languages: list[LanguageShare] = Field(default_factory=list)
    tech_keywords: list[str] = Field(default_factory=list)
    pinned_repos: list[RepoSummary] = Field(default_factory=list)
    top_repos: list[RepoSummary] = Field(default_factory=list)
    status: Literal["ok", "not_found", "skipped", "rate_limited", "error"] = "skipped"


class EnrichedProfile(CvExtract):
    github: GitHubProfile = Field(default_factory=GitHubProfile)
    merged_skills: list[str] = Field(default_factory=list)
    search_query: JobSearchQuery | None = None
