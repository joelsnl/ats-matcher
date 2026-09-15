"""Compare profile skills with job requirements using aliases and tool families."""
from __future__ import annotations

import re
from typing import TypedDict

from ats_matcher.schemas.jobs import Job

KNOWN_SKILLS = [
    "React", "TypeScript", "JavaScript", "CSS", "HTML", "SQL", "Python", "Excel",
    "Docker", "Figma", "User research", "Prototyping", "Product strategy",
    "Patient care", "Nursing", "Care planning", "Java", "AWS", "Git", "Node.js",
    "Project management", "Leadership", "Customer service",
    "Data analysis", "C++", "C#", "Go", "Rust", "Kubernetes", "PostgreSQL",
    "FastAPI", "Django", "Flask", "Linux", "Azure", "GCP", "Terraform", "Redis",
    "GraphQL", "MongoDB", "Spark", "Pandas", "NumPy", "Tableau", "Power BI",
    "Salesforce", "SAP", "Jira", "Agile", "Scrum", "CI/CD", "Machine learning",
    "Ansible", "Jenkins", "Grafana", "Prometheus", "Bash", "PowerShell",
    "GitHub Actions", "GitLab CI/CD", "Jenkins Pipelines", "K8s", "EKS",
    "Continuous Integration", "Continuous Delivery",
]

# Generic posting terms excluded from technical skill gap matching.
GENERIC_SKILLS = {
    "communication",
    "communications",
    "communication skills",
    "written communication",
    "verbal communication",
    "excellent communication",
    "teamwork",
    "team player",
    "collaboration",
    "collaborative",
    "interpersonal",
    "interpersonal skills",
    "problem solving",
    "problem-solving",
    "attention to detail",
    "time management",
    "self-motivated",
    "self motivated",
    "fast learner",
    "quick learner",
    "work ethic",
    "positive attitude",
    "multitasking",
    "multi-tasking",
    "organizational skills",
    "organisation skills",
}

# Same tool, different labels. First name is the canonical form.
ALIASES = [
    ["CI/CD", "CICD", "CI-CD", "CI CD", "Continuous Integration", "Continuous Delivery", "Continuous Deployment"],
    ["Kubernetes", "K8s"],
    ["Jenkins", "Jenkins Pipelines", "Jenkins Pipeline", "Jenkins CI"],
    ["GitHub Actions", "Github Actions", "GH Actions"],
    ["GitLab CI/CD", "GitLab CI", "Gitlab CI/CD", "Gitlab CI"],
    ["PostgreSQL", "Postgres"],
    ["Node.js", "NodeJS"],
    ["RHEL", "Red Hat", "Red Hat Enterprise Linux", "Redhat"],
    ["REST APIs", "REST API", "RESTful APIs", "RESTful"],
    ["AWS", "Amazon Web Services"],
    ["Azure", "Microsoft Azure"],
    ["GCP", "Google Cloud", "Google Cloud Platform"],
    ["Agile", "Agile (Scrum)", "Agile Scrum"],
]

# Umbrella terms are covered by any listed tool. Sibling tools do not replace each other:
# GitHub Actions covers CI/CD, not Jenkins. Docker does not cover Kubernetes.
FAMILIES = [
    {
        "umbrella": ["CI/CD"],
        "tools": [
            "Jenkins", "GitHub Actions", "GitLab CI/CD", "CircleCI",
            "Bitbucket Pipelines", "Azure DevOps", "Azure Pipelines", "Travis CI",
        ],
    },
    {
        "umbrella": ["Linux"],
        "tools": ["RHEL", "Ubuntu", "Debian", "CentOS", "Fedora"],
    },
    {
        "umbrella": ["Git", "Version Control"],
        "tools": ["GitHub", "GitLab", "Bitbucket"],
    },
    {
        "umbrella": ["Containers", "Containerization"],
        "tools": ["Docker"],
    },
    {
        "umbrella": ["Monitoring", "Observability", "Metrics", "Alerting"],
        "tools": ["Prometheus", "Grafana"],
    },
    {
        "umbrella": ["Logging"],
        "tools": ["Splunk", "ELK", "ELK Stack"],
    },
    {
        "umbrella": ["Access Control", "IAM", "Identity and Access Management"],
        "tools": ["LDAP", "Okta", "CyberArk", "SSO"],
    },
    {
        "umbrella": ["SQL"],
        "tools": ["PostgreSQL", "MySQL", "SQL Server", "SQLite", "MariaDB"],
    },
]


class SkillMatch(TypedDict):
    name: str
    via: list[str]


class SkillComparison(TypedDict):
    matched: list[SkillMatch]
    missing: list[str]


def skill_key(name: str) -> str:
    text = name.lower().strip().replace("&", " and ")
    text = re.sub(r"[/_\-]+", " ", text)
    text = re.sub(r"[^a-z0-9+.# ]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


_GENERIC_KEYS = {skill_key(item) for item in GENERIC_SKILLS}


def is_generic(name: str) -> bool:
    return skill_key(name) in _GENERIC_KEYS


def _token_pattern(label: str) -> re.Pattern[str]:
    return re.compile(r"(^|[^a-z0-9])" + re.escape(label) + r"([^a-z0-9]|$)", re.IGNORECASE)


def _contains_skill(haystack: str, needle: str) -> bool:
    if skill_key(haystack) == skill_key(needle):
        return True
    if skill_key(needle) == "azure":
        haystack = re.sub(r"\bAzure\s+(?:DevOps|Pipelines)\b", "", haystack, flags=re.I)
    return bool(_token_pattern(needle).search(haystack))


_ALIAS_CANONICAL: dict[str, str] = {}
for _group in ALIASES:
    _canonical = _group[0]
    for _label in _group:
        _ALIAS_CANONICAL[skill_key(_label)] = _canonical

_FAMILY_ROLE: dict[str, tuple[int, str]] = {}
_FAMILY_LABELS: list[str] = []
for _index, _family in enumerate(FAMILIES):
    for _role, _labels in (("umbrella", _family["umbrella"]), ("tool", _family["tools"])):
        for _label in _labels:
            _FAMILY_LABELS.append(_label)
            _key = skill_key(_ALIAS_CANONICAL.get(skill_key(_label), _label))
            _FAMILY_ROLE.setdefault(_key, (_index, _role))


def canonical_skill(name: str) -> str:
    return _ALIAS_CANONICAL.get(skill_key(name), name.strip())


def _family_role(name: str) -> tuple[int, str] | None:
    return _FAMILY_ROLE.get(skill_key(canonical_skill(name)))


def _catalog(extra: list[str] | None = None) -> dict[str, str]:
    seen: dict[str, str] = {}
    labels = [*KNOWN_SKILLS, *_FAMILY_LABELS]
    for group in ALIASES:
        labels.extend(group)
    labels.extend(extra or [])
    for skill in labels:
        name = skill.strip()
        if name and not is_generic(name):
            seen.setdefault(name.lower(), name)
    return seen


def mentioned_skills(body: str, extra: list[str] | None = None) -> list[str]:
    if not body:
        return []
    found = []
    for label in _catalog(extra).values():
        if _contains_skill(body, label):
            found.append(label)
    return found


def compare_skills(found: list[str], profile_skills: list[str]) -> SkillComparison:
    profile = [skill.strip() for skill in profile_skills if skill and skill.strip()]
    matched: list[SkillMatch] = []
    missing: list[str] = []
    seen: set[str] = set()
    for skill in found:
        name = skill.strip()
        key = skill_key(canonical_skill(name))
        if not name or is_generic(name) or key in seen:
            continue
        seen.add(key)
        via = _coverage(name, profile)
        if via is None:
            missing.append(name)
        else:
            matched.append({"name": name, "via": via})
    return {"matched": matched, "missing": missing}


def _coverage(job_skill: str, profile: list[str]) -> list[str] | None:
    job_canon = canonical_skill(job_skill)
    job_key = skill_key(job_canon)
    covered: list[str] = []
    same_name = False
    for item in profile:
        if is_generic(item):
            continue
        if skill_key(item) == skill_key(job_skill) or skill_key(canonical_skill(item)) == job_key:
            same_name = same_name or skill_key(item) == skill_key(job_skill)
            if skill_key(item) != skill_key(job_skill):
                covered.append(item)
            continue
        if _contains_skill(item, job_skill) or _contains_skill(item, job_canon):
            covered.append(item)
            continue
        covered.extend(_family_cover(job_canon, item))
    if same_name:
        return []
    if covered:
        best: dict[str, str] = {}
        for item in covered:
            key = skill_key(canonical_skill(item))
            previous = best.get(key)
            if previous is None or len(item) > len(previous):
                best[key] = item
        return list(best.values())
    return None


def _family_cover(job_canon: str, profile_skill: str) -> list[str]:
    job_role = _family_role(job_canon)
    profile_role = _family_role(profile_skill)
    if not job_role or not profile_role or job_role[0] != profile_role[0]:
        return []
    # Umbrella on the listing is covered by any family member on the profile.
    if job_role[1] == "umbrella":
        return [profile_skill]
    # Knowing an umbrella does not establish experience with a particular tool.
    return []


def score_job(job: Job, profile_skills: list[str]) -> Job:
    body = "\n".join(part for part in (job.title, job.description, job.translated_description) if part)
    found = mentioned_skills(body, profile_skills) or [skill for skill in job.skills if not is_generic(skill)]
    comparison = compare_skills(found, profile_skills)
    matched = [item["name"] for item in comparison["matched"]]
    profile_count = len([skill for skill in profile_skills if skill and skill.strip()])
    score = round(len(matched) / max(profile_count, 1), 4) if profile_count else 0.0
    return job.model_copy(update={"skills": found, "matched_skills": matched, "match_score": score})
