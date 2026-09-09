from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# Only labeled placements. Do not treat "Microsoft (Redmond)" or "IBM (NY)" as a client.
_CLIENT_PAREN = re.compile(
    r"^(?P<name>.+?)\s*\(\s*(?:client|customer|seconded(?:\s+to)?|via|consultant(?:\s+at)?)\s*:?\s+(?P<client>[^)]+?)\s*\)\s*$",
    re.IGNORECASE,
)


class Location(BaseModel):
    model_config = ConfigDict(extra="forbid")

    city: str | None = None
    region: str | None = None
    country: str | None = None
    raw: str | None = None


class Employer(BaseModel):
    """Hiring company, plus a client site when the CV states a placement."""

    model_config = ConfigDict(extra="forbid")

    name: str
    client: str | None = None


class SpokenLanguage(BaseModel):
    """A language the CV says the person speaks. level is omitted when unstated."""

    model_config = ConfigDict(extra="forbid")

    name: str
    level: str | None = None


class PossibleTitles(BaseModel):
    model_config = ConfigDict(extra="forbid")

    possible_titles: list[str] = Field(default_factory=list, max_length=8)


class CvExtract(BaseModel):
    """Structured fields extracted from a CV (LLM + regex merge)."""

    model_config = ConfigDict(extra="forbid")

    full_name: str | None = None
    email: str | None = None
    skills: list[str] = Field(default_factory=list, max_length=40)
    years_experience: float | None = Field(default=None, ge=0, le=60)
    primary_industry: str | None = None
    location: Location = Field(default_factory=Location)
    github_url: str | None = None
    linkedin_url: str | None = None
    recent_titles: list[str] = Field(default_factory=list, max_length=5)
    employers: list[Employer] = Field(default_factory=list, max_length=15)
    certifications: list[str] = Field(default_factory=list, max_length=15)
    spoken_languages: list[SpokenLanguage] = Field(default_factory=list, max_length=12)
    possible_titles: list[str] = Field(default_factory=list, max_length=8)
    birth_year: int | None = Field(default=None, ge=1920, le=2015)
    age_estimate: int | None = Field(default=None, ge=14, le=100)
    age_source: Literal["explicit_cv"] | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)

    @field_validator("employers", mode="before")
    @classmethod
    def _coerce_employers(cls, value: Any) -> list[dict[str, Any]]:
        if not value:
            return []
        return [row for row in (coerce_employer(item) for item in value) if row["name"]]

    @field_validator("spoken_languages", mode="before")
    @classmethod
    def _coerce_languages(cls, value: Any) -> list[dict[str, Any]]:
        if not value:
            return []
        return [row for row in (coerce_language(item) for item in value) if row["name"]]

    def public_dump(self, include_age: bool = False) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        data["employers"] = [_dump_employer(row) for row in data.get("employers") or []]
        data["spoken_languages"] = [_dump_language(row) for row in data.get("spoken_languages") or []]
        if include_age and self.age_source == "explicit_cv":
            return data
        data.pop("birth_year", None)
        data.pop("age_estimate", None)
        data.pop("age_source", None)
        return data

    def title_context(self) -> dict[str, Any]:
        """Facts used to infer possible_titles (no contact, age, or prior titles)."""
        data = self.model_dump(mode="json")
        employers = [_dump_employer(row) for row in data.get("employers") or []]
        languages = [_dump_language(row) for row in data.get("spoken_languages") or []]
        return {
            "skills": data.get("skills") or [],
            "certifications": data.get("certifications") or [],
            "spoken_languages": languages,
            "recent_titles": data.get("recent_titles") or [],
            "employers": employers,
            "years_experience": data.get("years_experience"),
            "primary_industry": data.get("primary_industry"),
            "location": data.get("location"),
        }


def cv_extract_llm_schema() -> dict[str, Any]:
    """Flattened JSON Schema for llama.cpp (no $ref / $defs)."""
    nullable_string = {"type": ["string", "null"]}
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "full_name",
            "email",
            "skills",
            "years_experience",
            "primary_industry",
            "location",
            "github_url",
            "linkedin_url",
            "recent_titles",
            "employers",
            "certifications",
            "spoken_languages",
            "birth_year",
            "age_estimate",
            "age_source",
            "confidence",
        ],
        "properties": {
            "full_name": nullable_string,
            "email": nullable_string,
            "skills": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 40,
            },
            "years_experience": {"type": ["number", "null"], "minimum": 0, "maximum": 60},
            "primary_industry": nullable_string,
            "location": {
                "type": "object",
                "additionalProperties": False,
                "required": ["city", "region", "country", "raw"],
                "properties": {
                    "city": nullable_string,
                    "region": nullable_string,
                    "country": nullable_string,
                    "raw": nullable_string,
                },
            },
            "github_url": nullable_string,
            "linkedin_url": nullable_string,
            "recent_titles": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 5,
            },
            "employers": {
                "type": "array",
                "maxItems": 15,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["name"],
                    "properties": {
                        "name": {"type": "string"},
                        "client": {"type": "string"},
                    },
                },
            },
            "certifications": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 15,
            },
            "spoken_languages": {
                "type": "array",
                "maxItems": 12,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["name"],
                    "properties": {
                        "name": {"type": "string"},
                        "level": {"type": "string"},
                    },
                },
            },
            "birth_year": {"type": ["integer", "null"], "minimum": 1920, "maximum": 2015},
            "age_estimate": {"type": ["integer", "null"], "minimum": 14, "maximum": 100},
            "age_source": {"type": ["string", "null"], "enum": ["explicit_cv", None]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
    }


def possible_titles_llm_schema() -> dict[str, Any]:
    """Second-pass schema: infer titles from an already-extracted profile."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["possible_titles"],
        "properties": {
            "possible_titles": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 8,
            },
        },
    }


def coerce_employer(item: Any) -> dict[str, str | None]:
    """Accept {name, client}, a plain company string, or 'Firm (Client: X)'."""
    if isinstance(item, Employer):
        name, client = item.name, item.client
    elif isinstance(item, str):
        name, client = item, None
    elif isinstance(item, dict):
        name = item.get("name") or ""
        client = item.get("client")
    else:
        raise TypeError(f"employer must be an object or string, got {type(item)!r}")

    name = name.strip() if isinstance(name, str) else ""
    if isinstance(client, str):
        client = client.strip() or None
    else:
        client = None

    match = _CLIENT_PAREN.match(name)
    if match and not client:
        name = match.group("name").strip()
        client = match.group("client").strip() or None
    row: dict[str, str | None] = {"name": name}
    if client:
        row["client"] = client
    return row


_LANG_LEVEL = re.compile(
    r"^(?P<name>.+?)\s*(?:\(|[-—–:])\s*(?P<level>"
    r"A1|A2|B1|B2|C1|C2|"
    r"native|mother\s*tongue|bilingual|fluent|"
    r"professional(?:\s+working)?|conversational|"
    r"intermediate|basic|proficient|advanced"
    r")(?:\s+level)?\s*\)?\s*$",
    re.IGNORECASE,
)


def coerce_language(item: Any) -> dict[str, str | None]:
    """Accept {name, level}, 'Dutch', or 'Dutch (A2)' / 'English — Native'."""
    if isinstance(item, SpokenLanguage):
        name, level = item.name, item.level
    elif isinstance(item, str):
        name, level = item, None
    elif isinstance(item, dict):
        name = item.get("name") or item.get("language") or ""
        level = item.get("level") or item.get("proficiency")
    else:
        raise TypeError(f"spoken language must be an object or string, got {type(item)!r}")

    name = name.strip() if isinstance(name, str) else ""
    if isinstance(level, str):
        level = level.strip() or None
    else:
        level = None

    match = _LANG_LEVEL.match(name)
    if match and not level:
        name = match.group("name").strip()
        level = match.group("level").strip()
    row: dict[str, str | None] = {"name": name}
    if level:
        row["level"] = level
    return row


def _dump_employer(row: dict[str, Any]) -> dict[str, str]:
    dumped = {"name": row["name"]}
    client = row.get("client")
    if client:
        dumped["client"] = client
    return dumped


def _dump_language(row: dict[str, Any]) -> dict[str, str]:
    dumped = {"name": row["name"]}
    level = row.get("level")
    if level:
        dumped["level"] = level
    return dumped
