from __future__ import annotations

import re
from dataclasses import dataclass, field

GITHUB_HOST = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)",
    re.IGNORECASE,
)
LINKEDIN_IN = re.compile(
    r"(?:https?://)?(?:[\w-]+\.)?linkedin\.com/in/([A-Za-z0-9_-]+)/?",
    re.IGNORECASE,
)
EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE = re.compile(
    r"(?<!\w)(?:\+\d{1,3}[\s.\-]?)?(?:\(?\d{2,4}\)?[\s.\-]?)?\d{3,4}[\s.\-]?\d{3,4}(?!\w)"
)
YEAR_RANGE = re.compile(
    r"(?P<start>(?:19|20)\d{2})\s*(?:[–\--]|to)\s*(?P<end>(?:19|20)\d{2}|present|now|current)",
    re.IGNORECASE,
)
BARE_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
YEARS_PHRASE = re.compile(
    r"\b(\d{1,2})\+?\s+years?(?:\s+of)?(?:\s+(?:professional|total))?(?:\s+experience)?\b",
    re.IGNORECASE,
)

_GITHUB_RESERVED = {
    "about",
    "apps",
    "collections",
    "customer-stories",
    "enterprise",
    "events",
    "explore",
    "features",
    "issues",
    "login",
    "marketplace",
    "new",
    "notifications",
    "org",
    "organizations",
    "pricing",
    "pulls",
    "security",
    "settings",
    "sponsors",
    "stars",
    "topics",
    "watch",
}


@dataclass
class RuleHints:
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    github_urls: list[str] = field(default_factory=list)
    github_usernames: list[str] = field(default_factory=list)
    linkedin_urls: list[str] = field(default_factory=list)
    year_ranges: list[tuple[int, int | None]] = field(default_factory=list)
    years: list[int] = field(default_factory=list)
    stated_years_experience: float | None = None

    @property
    def email(self) -> str | None:
        return self.emails[0] if self.emails else None

    @property
    def github_url(self) -> str | None:
        return self.github_urls[0] if self.github_urls else None

    @property
    def linkedin_url(self) -> str | None:
        return self.linkedin_urls[0] if self.linkedin_urls else None


def preextract(text: str) -> RuleHints:
    emails = _unique(EMAIL.findall(text))
    phones = _unique(_normalize_phone(m.group(0)) for m in PHONE.finditer(text) if _looks_like_phone(m.group(0)))

    github_urls: list[str] = []
    github_users: list[str] = []
    for match in GITHUB_HOST.finditer(text):
        user = match.group(1)
        if user.lower() in _GITHUB_RESERVED:
            continue
        url = f"https://github.com/{user}"
        if url not in github_urls:
            github_urls.append(url)
            github_users.append(user)

    linkedin_urls: list[str] = []
    for match in LINKEDIN_IN.finditer(text):
        slug = match.group(1)
        url = f"https://www.linkedin.com/in/{slug}"
        if url not in linkedin_urls:
            linkedin_urls.append(url)

    ranges: list[tuple[int, int | None]] = []
    for match in YEAR_RANGE.finditer(text):
        start = int(match.group("start"))
        end_raw = match.group("end")
        end = None if end_raw.lower() in {"present", "now", "current"} else int(end_raw)
        if end is not None and end < start:
            continue
        ranges.append((start, end))

    years = _unique(int(y) for y in BARE_YEAR.findall(text) if 1980 <= int(y) <= 2030)
    stated = None
    phrase = YEARS_PHRASE.search(text)
    if phrase:
        stated = float(min(60, int(phrase.group(1))))

    return RuleHints(
        emails=emails,
        phones=phones,
        github_urls=github_urls,
        github_usernames=github_users,
        linkedin_urls=linkedin_urls,
        year_ranges=ranges,
        years=years,
        stated_years_experience=stated,
    )


def _unique(items) -> list:
    seen: set[str] = set()
    out = []
    for item in items:
        key = str(item).lower() if not isinstance(item, int) else item
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _normalize_phone(raw: str) -> str:
    return re.sub(r"\s+", " ", raw).strip()


def _looks_like_phone(raw: str) -> bool:
    digits = re.sub(r"\D", "", raw)
    return 8 <= len(digits) <= 15
