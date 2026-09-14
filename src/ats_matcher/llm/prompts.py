from __future__ import annotations

import json

from ats_matcher.extract.rules import RuleHints
from ats_matcher.schemas.cv import CvExtract

SYSTEM_PROMPT = """You extract structured facts from a curriculum vitae in any industry or language.
Rules:
- Use only information present in the CV text. Never invent employers, dates, URLs, skills, certifications, or languages.
- location.country must be a full English country name. Expand codes such as NL to Netherlands. If a well-known city is stated without a country, fill that unambiguous country.
- If a field is not stated, use null (or an empty array for lists). Empty skills is valid when the CV has no skills list.
- github_url and email must be copied exactly when present; otherwise null.
- years_experience is total professional experience in years as a number, or null. Do not count only education as work experience.
- age_estimate and birth_year only if the CV explicitly states age or birth year. Otherwise null and age_source null.
- If age or birth year is explicit, set age_source to "explicit_cv".
- primary_industry is the main domain (software, healthcare, education, finance, trades, hospitality, public sector, etc.), or null.
- employers are objects, newest first. name is who paid or contracted the person (company, agency, hospital, school, self-employed, internship host). Include client only when the CV explicitly labels a client or placement (Client, Customer, seconded to, via). Parenthetical locations, divisions, or brands are not clients. If no client is mentioned, omit the client field - do not output null, and do not invent one. Never list a client as an employer unless they were also directly employed there.
- certifications are occupational certificates, licenses, or professional credentials stated on the CV. Copy names as written. Do not treat degrees, coursework, or language-test scores as certifications.
- spoken_languages are languages the CV says the person speaks. name is the language. Include level only when the CV states one (CEFR A1–C2, native, fluent, conversational, etc.). Omit level if unstated. Do not infer a level from nationality or location. Language-test scores (IELTS, TOEFL) are not languages unless a spoken language is also listed.
- Output JSON only. No markdown, no commentary.
"""

FIELD_GUIDE = """Fields:
- full_name (string|null)
- email (string|null)
- skills (string[], max 40) - professional skills as written; empty if none are listed
- years_experience (number|null)
- primary_industry (string|null)
- location: {city, region, country, raw} each string|null. city is the residence city if stated. country is the full English country name (Netherlands, not NL or NLD). If the CV names a well-known city without a country, fill that unambiguous country. Leave country null when the city could be in more than one country. raw is the location as written.
- github_url (string|null)
- linkedin_url (string|null)
- recent_titles (string[], max 5) - most recent job titles, newest first
- employers ({name, client?}[], max 15) - name = employer; client only if the CV labels a client/placement
- certifications (string[], max 15) - occupational certs and licenses only
- spoken_languages ({name, level?}[], max 12) - spoken languages; level only if stated
- birth_year (integer|null)
- age_estimate (integer|null)
- age_source ("explicit_cv"|null)
- confidence (number 0-1)
"""

TITLES_SYSTEM_PROMPT = """You infer market-standard job titles from an already-extracted CV profile.
Rules:
- Use only the extracted profile JSON. recent_titles are evidence of domain, not the output list - do not just copy them.
- Build titles from skills, work history, employers, occupational certifications, and spoken languages together. This may be any field (nursing, teaching, trades, product, finance, engineering, etc.). Languages only affect titles when the role is typically language-gated (e.g. a stated Dutch level for a Dutch-speaking customer role).
- employer.name is the hiring company. employer.client is a placement site when present; do not treat the client as the employer.
- If certifications contains occupational credentials (licenses or certs people are hired for), include at least one title a recruiter would search for that credential, combined with the person's background when that is natural. Ignore language tests, first-aid cards, and similar non-role certificates.
- Do not invent careers the profile does not support.
- Output JSON only. No markdown, no commentary.
"""

TITLES_FIELD_GUIDE = """Fields:
- possible_titles (string[], max 8) - market-standard titles this person could apply for
"""


def build_extract_messages(cv_text: str, hints: RuleHints) -> list[dict[str, str]]:
    hint_block = {
        "known_email": hints.email,
        "known_github": hints.github_url,
        "known_linkedin": hints.linkedin_url,
        "known_year_ranges": [{"start": a, "end": b} for a, b in hints.year_ranges],
    }
    user = (
        f"{FIELD_GUIDE}\n"
        f"Regex hints (prefer these for identifiers):\n"
        f"{json.dumps(hint_block, ensure_ascii=False)}\n\n"
        f"CV text:\n\"\"\"\n{cv_text}\n\"\"\"\n"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def build_repair_messages(
    cv_text: str,
    hints: RuleHints,
    previous: str,
    problems: list[str],
) -> list[dict[str, str]]:
    user = (
        "The previous JSON was invalid or incomplete. Output corrected JSON only.\n"
        f"Problems: {'; '.join(problems)}\n"
        f"Previous output:\n{previous}\n\n"
        f"Regex hints: email={hints.email}, github={hints.github_url}\n"
        f"CV (may be truncated):\n\"\"\"\n{cv_text[:4000]}\n\"\"\"\n"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def build_titles_messages(profile: CvExtract) -> list[dict[str, str]]:
    user = (
        f"{TITLES_FIELD_GUIDE}\n"
        f"{_certs_must_use(profile.certifications)}"
        f"Extracted profile:\n{json.dumps(profile.title_context(), ensure_ascii=False, indent=2)}\n"
    )
    return [
        {"role": "system", "content": TITLES_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def build_titles_repair_messages(
    profile: CvExtract,
    previous: str,
    problems: list[str],
) -> list[dict[str, str]]:
    user = (
        "The previous JSON was invalid or incomplete. Output corrected JSON only.\n"
        f"Problems: {'; '.join(problems)}\n"
        f"Previous output:\n{previous}\n\n"
        f"{_certs_must_use(profile.certifications)}"
        f"Extracted profile:\n{json.dumps(profile.title_context(), ensure_ascii=False)}\n"
    )
    return [
        {"role": "system", "content": TITLES_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _certs_must_use(certifications: list[str]) -> str:
    if not certifications:
        return ""
    listed = json.dumps(certifications, ensure_ascii=False)
    return (
        f"Occupational certifications on this profile: {listed}. "
        "If any of these are credentials people are hired for, include at least one matching market title.\n\n"
    )


def truncate_for_llm(text: str, max_chars: int = 24000) -> tuple[str, bool]:
    """Rough 6–8k token cap. Prefer contact + later sections if over budget."""
    if len(text) <= max_chars:
        return text, False
    head = text[: max_chars // 3]
    tail = text[-(max_chars - len(head) - 80) :]
    clipped = (
        head
        + "\n\n[... middle of CV omitted for length ...]\n\n"
        + tail
    )
    return clipped, True
