from __future__ import annotations

import re

from ats_matcher.extract.rules import RuleHints
from ats_matcher.schemas.cv import CvExtract, Location, coerce_employer, coerce_language

_SKILL_COMPACT = re.compile(r"[\s_\-]+")


def merge_extract(model: CvExtract, hints: RuleHints, include_age: bool = False) -> CvExtract:
    """Regex identifiers win over the model. Age is stripped unless opted in."""
    data = model.model_dump()
    if hints.email:
        data["email"] = hints.email
    if hints.github_url:
        data["github_url"] = hints.github_url
    if hints.linkedin_url:
        data["linkedin_url"] = hints.linkedin_url

    if not include_age or data.get("age_source") != "explicit_cv":
        data["birth_year"] = None
        data["age_estimate"] = None
        data["age_source"] = None

    data["skills"] = normalize_skills(data.get("skills") or [])
    data["recent_titles"] = normalize_strings(data.get("recent_titles") or [], limit=5)
    data["employers"] = normalize_employers(data.get("employers") or [])
    data["certifications"] = normalize_strings(data.get("certifications") or [], limit=15)
    data["spoken_languages"] = normalize_languages(data.get("spoken_languages") or [])
    data["possible_titles"] = normalize_strings(data.get("possible_titles") or [], limit=8)
    return CvExtract.model_validate(data)


def hints_to_cv(hints: RuleHints) -> CvExtract:
    """Rules-only fallback when no GGUF is loaded."""
    years = _estimate_years(hints)
    return CvExtract(
        email=hints.email,
        github_url=hints.github_url,
        linkedin_url=hints.linkedin_url,
        years_experience=years,
        location=Location(),
        confidence=0.25 if (hints.email or hints.github_url) else 0.1,
    )


def _estimate_years(hints: RuleHints) -> float | None:
    # Do not sum date ranges — education + jobs over-counts. Prefer an explicit phrase.
    return hints.stated_years_experience


def normalize_employers(items: list, limit: int = 15) -> list[dict[str, str | None]]:
    seen: set[str] = set()
    out: list[dict[str, str | None]] = []
    for item in items:
        row = coerce_employer(item)
        name = row["name"]
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out[:limit]


def normalize_languages(items: list, limit: int = 12) -> list[dict[str, str | None]]:
    seen: set[str] = set()
    out: list[dict[str, str | None]] = []
    for item in items:
        row = coerce_language(item)
        name = row["name"]
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out[:limit]


def normalize_skills(items: list[str], limit: int = 40) -> list[str]:
    """Dedupe skills that differ only by spaces or punctuation (any CV)."""
    compact_to_label: dict[str, str] = {}
    order: list[str] = []
    for item in items:
        label = item.strip()
        if not label:
            continue
        compact = _SKILL_COMPACT.sub("", label).lower()
        if not compact:
            continue
        if compact in compact_to_label:
            existing = compact_to_label[compact]
            preferred = _prefer_skill_label(existing, label)
            if preferred != existing:
                compact_to_label[compact] = preferred
                order[order.index(existing)] = preferred
            continue
        compact_to_label[compact] = label
        order.append(label)
    return order[:limit]


def _prefer_skill_label(existing: str, new: str) -> str:
    """Prefer 'Platform Engineering' over 'PlatformEngineering', not 'java script' over 'JavaScript'."""
    if " " in existing and " " not in new:
        return existing
    if " " not in existing and " " in new:
        if existing != existing.lower() and new == new.lower():
            return existing
        return new
    return existing


def normalize_strings(items: list[str], limit: int | None = None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip()
        if not key:
            continue
        low = key.lower()
        if low in seen:
            continue
        seen.add(low)
        out.append(key)
    if limit is not None:
        return out[:limit]
    return out
