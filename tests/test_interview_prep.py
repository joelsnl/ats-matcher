from ats_matcher.llm.engine import LlamaEngine
from ats_matcher.llm.interview_prep import generate_interview_prep, select_resources


PLATFORM = {
    "name": "Joel Sunil",
    "skills": ["Python", "GitHub Actions", "Jenkins Pipelines", "GitLab CI/CD", "Docker", "Ansible"],
    "roles": ["Platform Engineer"],
    "employers": [{"name": "Accenture", "client": "ASML"}],
}
PLATFORM_JOB = {
    "title": "Platform Engineer",
    "company": "Example",
    "description": "We need Python, CI/CD, Jenkins, Kubernetes, Prometheus and Linux for a platform team in Amsterdam.",
}


def test_select_resources_prefers_open_guides_for_the_listing():
    titles = [item["title"] for item in select_resources(PLATFORM, PLATFORM_JOB)]
    assert "Behavioral interview guide" in titles
    assert "DevOps Exercises" in titles
    assert any("Jenkins" in title or "GitHub Actions" in title or "Prometheus" in title for title in titles)
    assert "Kubernetes the Hard Way" in titles


def test_select_resources_skips_unrelated_engineering_labs():
    titles = [item["title"] for item in select_resources(
        {"name": "Taylor", "skills": ["Patient care"]},
        {"title": "Registered Nurse", "company": "Clinic", "description": "Provide person-centered nursing care and keep accurate care plans."},
    )]
    assert titles == ["Behavioral interview guide"]


def test_generate_without_a_model_still_returns_materials():
    pack = generate_interview_prep(None, PLATFORM, PLATFORM_JOB)
    assert pack["generated"] is False
    assert pack["resources"]
    assert "Kubernetes" in pack["briefing"]
    assert pack["ask_them"]
    assert pack["stories"] == []


def test_generate_stories_from_profile_facts():
    def complete(messages):
        joined = " ".join(item["content"] for item in messages)
        assert "interview stories for one real job" in joined
        assert "Accenture" in joined
        assert "GitHub Actions" in joined
        return """```json
        {
          "briefing": "This interview will spend time on the CI/CD work you already run at Accenture / ASML, not on pretending you operate Kubernetes daily.",
          "stories": [
            {"prompt": "Walk through a pipeline change that failed in production.", "anchor": "Accenture, Jenkins"},
            {"prompt": "When did you have to explain an operations trade-off to a non-engineer?", "anchor": "ASML"},
            {"prompt": "Tell me about teaching someone else a tool you already use.", "anchor": "GitHub Actions"}
          ],
          "ask_them": ["What does on-call actually look like on this team?"]
        }
        ```"""

    pack = generate_interview_prep(LlamaEngine(complete_fn=complete), PLATFORM, PLATFORM_JOB)
    assert pack["generated"] is True
    assert "Accenture" in pack["briefing"]
    assert len(pack["stories"]) == 3
    assert "on-call" in pack["ask_them"][0]
    assert pack["resources"]
