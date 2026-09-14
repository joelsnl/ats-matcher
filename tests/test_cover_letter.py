from ats_matcher.llm.cover_letter import (
    claimed_missing_tools,
    clean_cover_letter,
    generate_cover_letter,
    letter_looks_usable,
    pick_angle,
)
from ats_matcher.llm.engine import LlamaEngine


def test_clean_cover_letter_strips_model_preamble():
    raw = "Here's a cover letter:\n\nHi team,\n\nI shipped Jenkins pipelines at Accenture.\n"
    cleaned = clean_cover_letter(raw, "Joel Sunil")
    assert not cleaned.lower().startswith("here's")
    assert "Jenkins pipelines" in cleaned
    assert cleaned.endswith("Joel Sunil")


def test_usable_letter_rejects_stock_openings():
    assert letter_looks_usable("At Accenture I built GitHub Actions workflows for internal tools. That maps to the CI/CD work in this listing.\n\nI am already in Amsterdam.\n\nJoel")
    assert not letter_looks_usable("Dear Hiring Manager, I am writing to apply for this role.")


def test_refresh_picks_a_stable_angle_and_varies_across_retries():
    assert pick_angle("A|B", 0) == pick_angle("A|B", 0)
    assert len({pick_angle("A|B", i) for i in range(16)}) > 1


def test_claimed_missing_tools_allows_honest_gaps_and_rejects_invented_experience():
    missing = ["AWS", "EKS", "Terraform"]
    honest = (
        "My professional experience has primarily been in on-premise enterprise environments rather than AWS, "
        "and I have not yet had the same depth of production experience with EKS and Terraform that this position describes."
    )
    invented = (
        "At Accenture, I was a key part of ASML’s Engineering Services team. "
        "My background in managing production environments on AWS aligns well with the role."
    )
    assert claimed_missing_tools(honest, missing) == []
    assert claimed_missing_tools(invented, missing) == ["AWS"]
    assert not letter_looks_usable(invented, missing)
    assert letter_looks_usable(honest + "\n\nJoel Sunil", missing)


def test_generate_cover_letter_uses_facts_not_extract_json():
    letter = (
        "Dear Example team,\n\n"
        "I am applying for the Platform Engineer role because the CI/CD and Python work matches "
        "the GitHub Actions and Jenkins pipelines I have been running at Accenture, on assignment at ASML. "
        "I have not done Kubernetes in production and would not claim that experience.\n\n"
        "I am already in Amsterdam.\n\nJoel Sunil"
    )

    def complete(messages):
        joined = " ".join(item["content"] for item in messages)
        assert "plain-text application note" in joined
        assert "GitHub Actions" in joined
        assert "tools_you_must_not_claim" in joined
        assert "on assignment at ASML" in joined
        assert "Skip missing skills" not in joined
        return letter

    result = generate_cover_letter(
        LlamaEngine(complete_fn=complete),
        {
            "name": "Joel Sunil",
            "location": "Amsterdam, Netherlands",
            "skills": ["Python", "GitHub Actions", "Jenkins"],
            "employers": [{"name": "Accenture", "client": "ASML"}],
        },
        {
            "title": "Platform Engineer",
            "company": "Example",
            "description": "We need Python, CI/CD, Communication and Kubernetes for a platform team in Amsterdam.",
        },
    )
    assert "GitHub Actions" in result or "Jenkins" in result
    assert "I am writing to" not in result.lower()
    assert "kubernetes" in result.lower()


def test_generate_retries_when_the_first_draft_invents_cloud_experience():
    invented = (
        "Joining Example as a Senior Cloud Engineer feels like a natural progression. "
        "My background in managing production environments on AWS and setting up CI/CD pipelines aligns well with the role.\n\n"
        "Joel Sunil"
    )
    honest = (
        "Dear Example team,\n\n"
        "I am applying for the Senior Cloud Engineer role because the platform and CI/CD work matches "
        "the Jenkins pipelines I ran at Accenture, on assignment at ASML. "
        "I have not had production AWS, EKS, or Terraform experience, and I would not claim it.\n\n"
        "Joel Sunil"
    )
    calls = {"n": 0}

    def complete(messages):
        calls["n"] += 1
        joined = " ".join(item["content"] for item in messages)
        if calls["n"] == 1:
            return invented
        assert "AWS" in joined
        return honest

    result = generate_cover_letter(
        LlamaEngine(complete_fn=complete),
        {
            "name": "Joel Sunil",
            "skills": ["Python", "Jenkins"],
            "employers": [{"name": "Accenture", "client": "ASML"}],
        },
        {
            "title": "Senior Cloud Engineer",
            "company": "Example",
            "description": "Own AWS environments, EKS, Terraform and Jenkins CI/CD for a production platform.",
        },
    )
    assert calls["n"] == 2
    assert "have not had production AWS" in result
    assert "managing production environments on AWS" not in result
