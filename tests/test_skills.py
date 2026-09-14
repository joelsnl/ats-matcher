from ats_matcher.jobs.skills import compare_skills, mentioned_skills, score_job
from ats_matcher.schemas.jobs import Job

PROFILE = [
    "Python", "Perl", "Bash", "Groovy", "JavaScript", "Flask", "REST APIs",
    "Microservices", "Web Applications", "Internal Tools", "Data Pipelines",
    "System Integration", "Workflow Automation", "Linux", "RHEL", "Jenkins",
    "Bitbucket", "GitLab", "GitHub", "Apache HTTP Server", "Docker",
    "Jenkins Pipelines", "GitLab CI/CD", "GitHub Actions", "Ansible",
    "Repository Automation", "Deployment Automation", "Prometheus", "Grafana",
    "Splunk", "Logging", "Alerting", "Metrics", "Root Cause Analysis",
    "LDAP", "Okta", "CyberArk", "SSL/TLS", "Access Control", "Certificate Management",
]


def listing(**extra):
    return Job(
        title="Platform Engineer",
        company="Example",
        application_url="https://www.linkedin.com/jobs/view/1",
        job_id="1",
        source="linkedin",
        **extra,
    )


def test_generic_posting_language_is_not_extracted():
    assert "Communication" not in mentioned_skills("Excellent communication and Python.")
    assert mentioned_skills("Excellent communication and Python.") == ["Python"]


def test_ci_cd_is_covered_by_pipeline_tools():
    found = mentioned_skills("We need Python, CI/CD, Communication, and Kubernetes.")
    comparison = compare_skills(found, PROFILE)
    names = [item["name"] for item in comparison["matched"]]
    assert "Python" in names
    assert "CI/CD" in names
    ci = next(item for item in comparison["matched"] if item["name"] == "CI/CD")
    assert {"GitHub Actions", "Jenkins", "Jenkins Pipelines", "GitLab CI/CD"} & set(ci["via"])
    assert "Communication" not in found
    assert "Communication" not in comparison["missing"]
    assert "Kubernetes" in comparison["missing"]


def test_sibling_cloud_and_shell_tools_are_not_equated():
    comparison = compare_skills(["AWS", "Azure", "PowerShell", "Kubernetes", "Terraform"], PROFILE)
    assert comparison["matched"] == []
    assert comparison["missing"] == ["AWS", "Azure", "PowerShell", "Kubernetes", "Terraform"]


def test_linux_and_git_umbrellas_are_covered_by_specific_tools():
    comparison = compare_skills(["Linux", "Git", "Jenkins"], ["RHEL", "GitHub", "Jenkins Pipelines"])
    assert [item["name"] for item in comparison["matched"]] == ["Linux", "Git", "Jenkins"]


def test_score_job_counts_related_coverage():
    job = listing(description="Build services with Python, GitHub Actions, CI/CD and Communication.")
    scored = score_job(job, ["Python", "GitHub Actions", "Jenkins"])
    assert "CI/CD" in scored.matched_skills
    assert "Python" in scored.matched_skills
    assert "Communication" not in scored.skills
    assert "Communication" not in scored.matched_skills
