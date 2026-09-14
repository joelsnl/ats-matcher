"""Traceable requirements for writing and coaching. Absence is not inability."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from ats_matcher.jobs.skills import ALIASES, canonical_skill, compare_skills, mentioned_skills, skill_key

# These are practice topics, never a personality score or a claim of competence.
SOFT_TOPICS = {
    "Communication": ("communication", "communicate", "explain", "explained", "presenting", "presentation", "stakeholder", "stakeholders", "communicatief", "communicatie"),
    "Collaboration": ("collaboration", "collaborate", "collaborated", "cross-functional", "teamwork", "samenwerken", "samenwerking"),
    "Leadership": ("leadership", "mentoring", "mentor", "mentored", "coaching", "coach", "coached", "leiderschap", "begeleiden"),
    "Problem solving": ("problem solving", "problem-solving", "troubleshoot", "root cause", "analytical", "analytisch"),
    "Prioritization": ("prioritization", "prioritisation", "prioritize", "prioritise", "deadlines", "time management", "prioriteiten"),
    "Conflict resolution": ("conflict", "disagreement", "negotiate", "negotiation", "onderhandelen"),
}
_OPTIONAL = re.compile(r"\b(nice[- ]to[- ]have|preferred|desirable|bonus|a plus|ideally|optional|preference|pré|pre|voorkeur)\b", re.I)
_REQUIRED = re.compile(r"\b(must|required|essential|requirements?|need|proficient|strong|vereist|verplicht)\b", re.I)
_NEGATIVE = re.compile(r"\b(no|not|never|without|haven['’]?t|have not|geen|niet)\b", re.I)
_LEARNING = re.compile(r"\b(learning|studying|beginner|introductory|course|tutorial|aspiring|want to|would like|interested in)\b", re.I)
_ACTION = re.compile(r"\b(built|wrote|maintained|implemented|developed|designed|delivered|created|tested|deployed|managed|operated|used|led|mentored|coached|explained|resolved|automated|reduced|supported|onderhouden|ontwikkeld|gebouwd|geschreven|uitgelegd)\b", re.I)
_LOGGED_RECORDS = re.compile(r"\blogged\s+(?:(?:invalid|error|failed|validation|diagnostic)\s+)?(?:rows|entries|events|errors|messages|requests|failures|records)\b", re.I)


def token_pattern(label: str) -> re.Pattern[str]:
    return re.compile(r"(?<![\w])" + re.escape(label) + r"(?![\w])", re.I)


def labels_for(name: str) -> list[str]:
    key = skill_key(canonical_skill(name))
    labels = [name]
    for group in ALIASES:
        if skill_key(group[0]) == key:
            labels.extend(group)
    return list(dict.fromkeys(labels))


def snippets(body: str) -> list[str]:
    # Preserve a quote rather than reconstructing model-supplied evidence.
    return [s.strip(" \t-•")[:650] for s in re.split(r"\n+|(?<=[.!?;])\s+", body) if s.strip()]


def _contains(body: str, labels: list[str] | tuple[str, ...]) -> bool:
    if "Azure" in labels:
        body = re.sub(r"\bAzure\s+(?:DevOps|Pipelines)\b", "", body, flags=re.I)
    return any(token_pattern(label).search(body) for label in labels)


def _priority(quote: str) -> str:
    if _OPTIONAL.search(quote):
        return "preferred"
    if _REQUIRED.search(quote):
        return "required"
    return "mentioned"


def _requirements(description: str, extras: list[str]) -> list[dict[str, str]]:
    found: dict[str, dict[str, str]] = {}
    section = "mentioned"
    for line in snippets(description):
        # A short section heading also informs following bullet points.
        if len(line) < 90 and (line.endswith(":") or line.lower() in {"requirements", "nice to have", "preferred qualifications", "required qualifications"}):
            section = _priority(line)
        names = mentioned_skills(line, extras)
        names.extend(name for name, labels in SOFT_TOPICS.items() if _contains(line, labels))
        for label in names:
            name = canonical_skill(label)
            # "Go the extra mile" is not the programming language.
            if name == "Go" and not (line.strip(" .-*") == "Go" or re.search(r"\bGo\b", line) and re.search(r"\b(?:Golang|language|programming|developer|engineer|backend|Python|Java|Rust|TypeScript)\b|\b(?:using|with|in) Go\b", line, re.I)):
                continue
            # A waived requirement is neither a gap nor a reason to reject someone.
            waived = any(re.search(r"\b(?:no|not)\s+(?:prior\s+)?" + re.escape(alias) + r"\s+(?:experience\s+)?(?:needed|required|necessary)\b", line, re.I)
                         or re.search(re.escape(alias) + r"\s+(?:experience\s+)?(?:is\s+)?not\s+(?:needed|required|necessary)\b", line, re.I)
                         for alias in labels_for(name))
            if waived:
                continue
            priority = _priority(line)
            if priority == "mentioned":
                priority = section
            key = skill_key(name)
            row = {"id": hashlib.sha256(key.encode()).hexdigest()[:12], "name": name,
                   "kind": "soft" if name in SOFT_TOPICS else "hard", "priority": priority, "job_evidence": line}
            old = found.get(key)
            rank = {"required": 0, "mentioned": 1, "preferred": 2}
            if old is None or rank[priority] < rank[old["priority"]]:
                found[key] = row
    return list(found.values())[:60]


def build_role_context(profile: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    skills = [s.strip() for s in profile.get("skills", []) if isinstance(s, str) and s.strip()]
    confirmed = [s for s in skills if not _NEGATIVE.search(s) and not _LEARNING.search(s)]
    cv = str(profile.get("cv_text") or "")[:12000]
    examples = str(profile.get("achievements") or "")[:3000]
    evidence_lines = [("Your example", q) for q in snippets(examples)] + [("CV excerpt", q) for q in snippets(cv)]
    requirements = _requirements(str(job.get("description") or ""), skills)
    for row in requirements:
        name = row["name"]
        labels = SOFT_TOPICS.get(name, tuple(labels_for(name)))
        quotes = [(source, q) for source, q in evidence_lines
                  if (_contains(q, labels) or (name == "Logging" and _LOGGED_RECORDS.search(q)))
                  and not _NEGATIVE.search(q) and not _LEARNING.search(q)]
        comparison = compare_skills([name], confirmed)
        match = comparison["matched"][0] if comparison["matched"] else None
        if quotes:
            source, quote = quotes[0]
            status = "example" if _ACTION.search(quote) else "cv_mention"
        elif match:
            via = match["via"]
            direct = any(skill_key(canonical_skill(s)) == skill_key(name) for s in confirmed)
            status = "listed" if direct else "related"
            source, quote = "Profile skills", ", ".join(via) if via else name
        else:
            status, source, quote = "not_evidenced", "", ""
            for candidate_source, candidate_quote in evidence_lines:
                if _NEGATIVE.search(candidate_quote) or _LEARNING.search(candidate_quote):
                    continue
                if compare_skills([name], mentioned_skills(candidate_quote, skills))["matched"]:
                    status, source, quote = "related", candidate_source, candidate_quote
                    break
        row.update(status=status, evidence_source=source, profile_evidence=quote)
        row["mode"] = "rehearsal" if row["kind"] == "soft" else "refresher" if status != "not_evidenced" else "foundation"
    # Simple explicit alternatives: knowing Python in "Python or Java" should
    # not put learning Java ahead of an unmet Kubernetes requirement.
    for row in requirements:
        alternatives = []
        if row["kind"] == "hard":
            for other in requirements:
                if row["id"] == other["id"] or other["kind"] != "hard" or row["job_evidence"] != other["job_evidence"]:
                    continue
                if any(re.search(r"(?<!\w)" + re.escape(a) + r"\s+(?:or|of)\s+" + re.escape(b) + r"(?!\w)", row["job_evidence"], re.I)
                       for a in labels_for(row["name"]) for b in labels_for(other["name"])) or any(
                    re.search(r"(?<!\w)" + re.escape(b) + r"\s+(?:or|of)\s+" + re.escape(a) + r"(?!\w)", row["job_evidence"], re.I)
                    for a in labels_for(row["name"]) for b in labels_for(other["name"])):
                    alternatives.append(other)
        row["alternatives"] = [r["name"] for r in alternatives]
        row["alternative_covered"] = row["status"] == "not_evidenced" and any(r["status"] != "not_evidenced" for r in alternatives)
    material = json.dumps({"profile": profile, "job": job}, sort_keys=True, ensure_ascii=False)
    return {
        "version": 1, "fingerprint": hashlib.sha256(material.encode()).hexdigest()[:20],
        "requirements": requirements,
        "summary": {
            "supported": sum(r["status"] != "not_evidenced" for r in requirements if r["kind"] == "hard"),
            "not_evidenced": sum(r["status"] == "not_evidenced" for r in requirements if r["kind"] == "hard"),
            "people_skills": sum(r["kind"] == "soft" for r in requirements),
        },
        "limitations": "A mention is evidence to review, not proof of proficiency. Missing from the CV means unknown, not unable. Requirement labels are text-based estimates; check the quoted listing.",
    }


def writing_facts(profile: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Only career evidence belongs in the factual part of a writing prompt."""
    rows = context["requirements"]
    return {
        "name": profile.get("name"),
        "years_experience": profile.get("years_experience"),
        "recent_titles": profile.get("recent_titles") or [],
        "skills": profile.get("skills") or [],
        "employers": profile.get("employers") or [],
        "certifications": profile.get("certifications") or [],
        "real_examples": str(profile.get("achievements") or "")[:3000],
        "cv_excerpt": str(profile.get("cv_text") or "")[:3500],
        "requirement_evidence": [{**r, "job_evidence": r["job_evidence"][:220], "profile_evidence": r["profile_evidence"][:220]} for r in rows[:16]],
        "not_evidenced": [r["name"] for r in rows if r["kind"] == "hard" and r["status"] == "not_evidenced"],
    }
