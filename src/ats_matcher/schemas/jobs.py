from __future__ import annotations

from typing import Annotated, Literal
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator


JobType = Literal["full_time", "part_time", "contract", "temporary", "volunteer", "internship"]
WorkplaceType = Literal["on_site", "remote", "hybrid"]
ExperienceLevel = Literal["internship", "entry_level", "associate", "senior", "director", "executive"]


class JobSearchQuery(BaseModel):
    """Provider-neutral options; also accepts linkedin-jobs-api option names."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)
    keywords: str = Field(min_length=1, max_length=300, validation_alias=AliasChoices("keywords", "keyword"))
    location: str | None = Field(default=None, max_length=200)
    career_url: str | None = Field(default=None, max_length=2000)
    date_since_posted: Literal["any", "past_month", "past_week", "24hr"] = Field(default="past_week", validation_alias=AliasChoices("date_since_posted", "dateSincePosted"))
    posted_within_days: int | None = Field(default=None, ge=1, le=365, strict=True, validation_alias=AliasChoices("posted_within_days", "postedWithinDays"))
    job_type: JobType | Annotated[list[JobType], Field(min_length=1, max_length=6)] | None = Field(default=None, validation_alias=AliasChoices("job_type", "jobType"))
    workplace_type: WorkplaceType | Annotated[list[WorkplaceType], Field(min_length=1, max_length=3)] | None = Field(default=None, validation_alias=AliasChoices("workplace_type", "remoteFilter"))
    salary: Literal[40000, 60000, 80000, 100000, 120000] | None = None
    experience_level: ExperienceLevel | Annotated[list[ExperienceLevel], Field(min_length=1, max_length=6)] | None = Field(default=None, validation_alias=AliasChoices("experience_level", "experienceLevel"))
    sort_by: Literal["recent", "relevant"] = Field(default="relevant", validation_alias=AliasChoices("sort_by", "sortBy"))
    limit: int = Field(default=15, ge=1, le=100)
    page: int = Field(default=0, ge=0, le=1000)
    has_verification: bool = False
    under_10_applicants: bool = False
    indeed_country: str | None = Field(default=None, max_length=20)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_filters(cls, value):
        if not isinstance(value, dict):
            return value
        data = dict(value)
        mappings = {
            "f_TPR": ("date_since_posted", {"r86400": "24hr", "r604800": "past_week", "r2592000": "past_month", "": "any"}),
            "f_E": ("experience_level", {"1": "internship", "2": "entry_level", "3": "associate", "4": "senior", "5": "director", "6": "executive"}),
            "f_WT": ("workplace_type", {"1": "on_site", "2": "remote", "3": "hybrid"}),
        }
        for key, (target, choices) in mappings.items():
            if key in data:
                raw = data.pop(key)
                if raw is not None:
                    if not isinstance(raw, str) or raw not in choices:
                        raise ValueError(f"Unsupported legacy filter {key}")
                    if target in data and data[target] != choices[raw]:
                        raise ValueError(f"Conflicting filters for {target}")
                    data[target] = choices[raw]
        return data

    @field_validator("date_since_posted", "sort_by", mode="before")
    @classmethod
    def normalize_option(cls, value):
        if isinstance(value, str):
            value = "_".join(value.strip().lower().replace("-", " ").split())
            if not value:
                return None
        return "24hr" if value == "24h" else value

    @field_validator("job_type", "workplace_type", "experience_level", mode="before")
    @classmethod
    def normalize_multi_option(cls, value):
        # Preserve single-value callers; accept JSON arrays and CLI comma lists.
        if isinstance(value, str) and "," in value:
            value = value.split(",")
        if isinstance(value, list):
            if not value or any(not isinstance(item, str) or not item.strip() for item in value):
                raise ValueError("Choose at least one non-empty filter value, or omit the filter for any value")
            normalized = [cls.normalize_option(item) for item in value]
            if any(item is None for item in normalized):
                raise ValueError("Filter values must not be empty")
            return sorted(set(normalized))
        return cls.normalize_option(value)

    @field_validator("salary", mode="before")
    @classmethod
    def normalize_salary(cls, value):
        if value == "":
            return None
        return int(value) if isinstance(value, str) and value.isdigit() else value


class Job(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1)
    company: str = Field(min_length=1)
    location: str | None = None
    posted_at: str | None = None
    posted_relative: str | None = None
    application_url: str
    job_id: str
    source: str = "linkedin"
    company_logo: str | None = None
    salary: str | None = None
    description: str | None = Field(default=None, max_length=20000)
    source_language: str | None = Field(default=None, max_length=12)
    translated_description: str | None = Field(default=None, max_length=20000)
    translation_language: str | None = Field(default=None, max_length=12)
    skills: list[str] = Field(default_factory=list)
    matched_skills: list[str] = Field(default_factory=list)
    match_score: float | None = Field(default=None, ge=0, le=1)
    employment_type: Literal["full_time", "part_time", "contract", "internship", "temporary", "volunteer"] | None = None
    workplace_type: Literal["on_site", "remote", "hybrid"] | None = None
    easy_apply: bool | None = None
    external_apply_url: str | None = None

    @field_validator("application_url", "company_logo", "external_apply_url")
    @classmethod
    def web_urls_only(cls, value):
        if value is not None:
            from urllib.parse import urlsplit
            parsed = urlsplit(value)
            if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("Expected an http(s) URL")
        return value

    @field_validator("external_apply_url")
    @classmethod
    def company_apply_urls_only(cls, value):
        if value is None:
            return None
        from urllib.parse import urlsplit
        host = (urlsplit(value).hostname or "").lower()
        if host == "linkedin.com" or host.endswith(".linkedin.com"):
            return None
        return value


class ProviderReadiness(BaseModel):
    """Metadata about a provider's readiness and capabilities."""
    kind: Literal["job_site", "company_board"] = "job_site"
    available: bool = True
    unavailable_reason: str | None = None
    configured_boards: int = 0
    supported_filters: list[str] = Field(default_factory=list)
    unsupported_filters: list[str] = Field(default_factory=list)
    default_date_behavior: str = "any"
    countries: list[str] = Field(default_factory=list)
    requires_dependency: str | None = None
    last_check: str | None = None


class ProviderStatus(BaseModel):
    provider: str
    status: Literal["ok", "partial", "error"] = "ok"
    returned: int = 0
    cached: bool = False
    pages_fetched: int = 0
    next_page: int | None = None
    warnings: list[str] = Field(default_factory=list)
    error_code: str | None = None
    error: str | None = None
    retry_after: int | None = None
    readiness: ProviderReadiness | None = None


class ProviderResult(ProviderStatus):
    jobs: list[Job] = Field(default_factory=list)


class JobsMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requested: int
    returned: int
    provider: str
    status: Literal["ok", "partial", "error"] = "ok"
    query_used: JobSearchQuery | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    providers: list[ProviderStatus] = Field(default_factory=list)


class JobSearchResponse(BaseModel):
    jobs: list[Job] = Field(default_factory=list)
    jobs_meta: JobsMeta
