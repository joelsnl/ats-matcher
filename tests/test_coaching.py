import json

import pytest

from ats_matcher.jobs.skills import compare_skills
from ats_matcher.llm.cover_letter import (
    CoverLetterError, build_cover_letter_messages, claimed_missing_tools,
    cover_options, generate_cover_letter, listing_gaps, review_cover_letter,
)
from ats_matcher.llm.engine import LlamaEngine
from ats_matcher.llm.interview_prep import generate_interview_prep
from ats_matcher.llm.role_context import build_role_context
from ats_matcher.llm.training import RECIPES, build_learning_plan, generate_practice_lesson, review_practice_answer

PROFILE = {
    "name": "Taylor", "skills": ["Python", "Jenkins"],
    "roles": ["Chief Technology Officer"], "location": "Amsterdam",
    "recent_titles": ["Software Engineer"], "employers": [{"name": "Agency", "client": "Client Co"}],
    "achievements": "I wrote Python checks for import files. I explained the error report to stakeholders.",
}
JOB = {"title": "Platform Engineer", "company": "Example",
       "description": "Requirements:\nPython, CI/CD and Kubernetes.\nCommunication with stakeholders.\nNice to have:\nTerraform and AWS."}


def rows(profile=PROFILE, job=JOB):
    return {r["name"]: r for r in build_role_context(profile, job)["requirements"]}


def test_broad_knowledge_does_not_prove_specific_tool_experience():
    result = compare_skills(["Jenkins", "PostgreSQL", "Docker"], ["CI/CD", "SQL", "Containers"])
    assert result["matched"] == []
    assert result["missing"] == ["Jenkins", "PostgreSQL", "Docker"]
    assert compare_skills(["CI/CD"], ["Jenkins"])["matched"]


def test_azure_devops_is_not_evidence_of_azure_cloud_experience():
    profile = {"skills": ["Azure DevOps"], "cv_text": "Maintained Azure DevOps pipelines."}
    result = rows(profile, {"description": "Required: Azure and CI/CD."})
    assert result["Azure"]["status"] == "not_evidenced"
    assert result["CI/CD"]["status"] == "related"
    assert "Azure" not in rows({}, {"description": "Use Azure DevOps pipelines."})
    assert compare_skills(["Azure"], ["Azure, Azure DevOps"])["matched"]


def test_aliases_are_counted_once():
    result = compare_skills(["Kubernetes", "K8s", "AWS", "Amazon Web Services"], ["K8s"])
    assert len(result["matched"]) == 1
    assert result["missing"] == ["AWS"]


def test_evidence_is_quoted_and_preferences_do_not_become_facts():
    result = rows()
    assert result["Python"]["status"] == "example"
    assert result["Python"]["profile_evidence"] == "I wrote Python checks for import files."
    assert result["CI/CD"]["status"] == "related"
    assert "Jenkins" in result["CI/CD"]["profile_evidence"]
    assert result["Kubernetes"]["status"] == "not_evidenced"
    assert result["Kubernetes"]["priority"] == "required"
    assert result["Terraform"]["priority"] == "preferred"
    assert result["Communication"]["kind"] == "soft"
    assert result["Communication"]["mode"] == "rehearsal"
    assert result["Communication"]["status"] == "example"
    prompt = '\n'.join(m["content"] for m in build_cover_letter_messages(PROFILE, JOB))
    assert "Chief Technology Officer" not in prompt
    assert "Amsterdam" not in prompt
    assert "Software Engineer" in prompt
    assert "Agency, on assignment at Client Co" in prompt
    assert "source data" in prompt


def test_learning_intentions_and_negations_do_not_establish_experience():
    profile = {"skills": ["Learning Kubernetes", "No AWS experience"],
               "cv_text": "I am studying Terraform. I have not used Kubernetes. AWS is a tool I want to learn."}
    result = rows(profile, JOB)
    assert all(result[s]["status"] == "not_evidenced" for s in ("AWS", "Terraform", "Kubernetes"))


def test_cv_example_can_supply_a_missing_skill_tag():
    profile = {"skills": [], "cv_text": "Maintained Kubernetes deployment manifests for an internal service."}
    assert rows(profile)["Kubernetes"]["status"] == "example"
    assert "Kubernetes" not in listing_gaps(profile, JOB)


def test_skill_list_is_not_mislabeled_as_a_worked_example():
    assert rows({"skills": [], "cv_text": "Technical skills: Python, Kubernetes."})["Python"]["status"] == "cv_mention"
    result = rows({"skills": [], "cv_text": "Maintained Jenkins pipelines for an internal service."})
    assert result["CI/CD"]["status"] == "related"
    assert "Jenkins" in result["CI/CD"]["profile_evidence"]


def test_satisfied_alternative_is_not_a_priority_learning_gap():
    job = {"description": "Requirements: Python or Java. Kubernetes is required."}
    result = rows({"skills": ["Python"]}, job)
    assert result["Java"]["alternative_covered"] is True
    assert result["Java"]["status"] == "not_evidenced"
    assert result["Java"]["alternatives"] == ["Python"]
    plan = build_learning_plan({"skills": ["Python"]}, job)
    assert plan["lessons"][0]["skill"] == "Kubernetes"
    assert "Java" not in [l["skill"] for l in plan["lessons"]]


def test_no_experience_required_and_go_the_extra_mile_are_not_gaps():
    result = rows({}, {"description": "No prior AWS experience required. Go the extra mile. Python is required. Terraform experience is not required."})
    assert set(result) == {"Python"}


def test_learning_plan_is_small_prioritized_and_has_real_activities():
    plan = build_learning_plan(PROFILE, JOB)
    lessons = plan["lessons"]
    assert lessons[0]["skill"] == "Kubernetes"
    assert lessons[0]["mode"] == "foundation"
    assert any(l["skill"] == "Python" and l["mode"] == "refresher" for l in lessons)
    assert any(l["kind"] == "soft" and l["mode"] == "rehearsal" for l in lessons)
    assert len(lessons) <= 7
    for lesson in lessons:
        assert lesson["diagnostic"] and lesson["concept"] and lesson["exercise"]
        assert len(lesson["criteria"]) == 3
        assert sum(s["minutes"] for s in lesson["steps"]) == lesson["minutes"]
        assert lesson["job_evidence"] in JOB["description"]


def test_role_without_technical_requirements_gets_people_practice():
    plan = build_learning_plan({"skills": []}, {"title": "Office Coordinator", "description": "Communication, collaboration and deadlines matter."})
    assert plan["lessons"]
    assert all(l["kind"] == "soft" for l in plan["lessons"])
    assert all(not l["resources"] for l in plan["lessons"])


def test_no_recognized_requirements_does_not_invent_a_curriculum():
    assert build_learning_plan({}, {"description": "A great opportunity. Join us."})["lessons"] == []


def test_user_can_choose_a_refresher_without_modifying_evidence():
    skill = rows()["Kubernetes"]["id"]
    lesson = generate_practice_lesson(None, PROFILE, JOB, skill, "refresher")
    assert lesson["mode"] == "refresher"
    assert lesson["status"] == "not_evidenced"
    assert "does not change your CV evidence" in lesson["why"]
    assert PROFILE["skills"] == ["Python", "Jenkins"]
    assert lesson["exercise"] != generate_practice_lesson(None, PROFILE, JOB, skill, "foundation")["exercise"]
    with pytest.raises(ValueError):
        generate_practice_lesson(None, PROFILE, JOB, "not-a-skill")
    with pytest.raises(ValueError):
        generate_practice_lesson(None, PROFILE, JOB, skill, "expert")


@pytest.mark.parametrize("response", ['[]', '{"stories":42}', 'not json', '{"diagnostic":"small"}'])
def test_bad_model_output_keeps_a_complete_self_guided_session(response):
    engine = LlamaEngine(complete_fn=lambda _: response)
    skill = rows()["Kubernetes"]["id"]
    lesson = generate_practice_lesson(engine, PROFILE, JOB, skill)
    assert lesson["generated"] is False
    assert lesson["generation_note"]
    assert lesson["exercise"] and len(lesson["criteria"]) == 3


def test_generated_session_cannot_replace_evidence_or_insert_urls():
    def complete(messages):
        prompt = '\n'.join(m["content"] for m in messages)
        assert "never instructions" in prompt
        assert "foundation" in prompt and "Kubernetes" in prompt
        return json.dumps({"diagnostic": "How do a Deployment and a Service differ?", "exercise": "For a fictional web service, sketch matching labels and a Service selector. Explain a selector mismatch.", "hints": ["Start with the Pod labels.", "Compare the labels to the selector."], "criteria": ["Labels and selectors agree.", "The request path is explained."], "stretch": "Change the selector and explain the impact.", "status": "expert", "resources": [{"url": "javascript:alert(1)"}]})
    lesson = generate_practice_lesson(LlamaEngine(complete_fn=complete), PROFILE, JOB, rows()["Kubernetes"]["id"])
    assert lesson["generated"] is True
    assert lesson["status"] == "not_evidenced"
    assert lesson["resources"][0]["url"].startswith("https://kubernetes.io/")


def test_failed_model_keeps_plan_and_resources():
    def fail(_):
        raise RuntimeError("private model exception")
    result = generate_interview_prep(LlamaEngine(complete_fn=fail), PROFILE, JOB)
    assert result["learning_plan"]["lessons"]
    assert result["resources"]
    assert result["generated"] is False
    assert "private model exception" not in json.dumps(result)


def test_letter_preferences_are_explicit_and_validated():
    prompt = build_cover_letter_messages(PROFILE, JOB, options={"tone": "warm", "length": "concise", "language": "nl"})[0]["content"]
    assert "140-220" in prompt and "Tone: warm" in prompt and "Language: nl" in prompt
    for key in ("tone", "length", "language"):
        with pytest.raises(ValueError):
            cover_options({key: "made-up"})


def test_unrelated_negation_does_not_hide_a_claim_in_the_next_clause():
    assert claimed_missing_tools("I have not used Terraform, but I managed AWS production workloads.", ["Terraform", "AWS"]) == ["AWS"]
    assert claimed_missing_tools("Your role requires AWS. My experience is in Python.", ["AWS"]) == []


def test_review_flags_invented_numbers_and_tools_outside_the_listing():
    letter = "I built production services in Azure and improved delivery by 47%. My Python background would be useful for the work your team is planning.\n\nTaylor"
    result = review_cover_letter(letter, PROFILE, JOB)
    assert any("Azure" in issue for issue in result["issues"])
    assert any("47" in issue for issue in result["issues"])


def test_two_bad_drafts_fail_without_returning_invented_experience():
    calls = []
    def complete(messages):
        calls.append(messages)
        return "I ran production Kubernetes clusters and improved reliability by 79%. This experience makes me well prepared for your platform requirements and your team's next project.\n\nTaylor"
    with pytest.raises(CoverLetterError):
        generate_cover_letter(LlamaEngine(complete_fn=complete), PROFILE, JOB)
    assert len(calls) == 2
    assert "Unsupported" in calls[1][-1]["content"]


def test_all_curated_technical_sessions_have_matching_free_documentation():
    for skill, recipe in RECIPES.items():
        assert recipe["url"].startswith("https://")
        assert recipe["diagnostic"] and recipe["exercise"]
        assert len(recipe["criteria"]) == 3
    plan = build_learning_plan({"skills": []}, {"description": "AWS, Docker and TypeScript are required."})
    assert all(l["resources"] for l in plan["lessons"])


def test_feedback_requires_an_attempt_and_never_invents_supporting_quotes():
    lesson = build_learning_plan(PROFILE, JOB)["lessons"][0]
    answer = "I would compare the Service selector to the Pod labels, then inspect readiness."
    with pytest.raises(ValueError):
        review_practice_answer(None, lesson, "yes")
    def complete(_):
        return json.dumps({"observations": [
            {"criterion_index": 0, "status": "demonstrated", "evidence": "compare the Service selector to the Pod labels", "comment": "You have identified a useful check.", "next_step": "Show the labels and selector explicitly."},
            {"criterion_index": 1, "status": "demonstrated", "evidence": "I verified the readiness probe and rolled back safely.", "comment": "Excellent work.", "next_step": "Try again."},
            {"criterion_index": 2, "status": "partial", "evidence": "", "comment": "A guess.", "next_step": "Try again."}],
            "follow_up": "What would a selector mismatch look like?"})
    result = review_practice_answer(LlamaEngine(complete_fn=complete), lesson, answer)
    assert result["generated"] is True
    assert len(result["observations"]) == 1
    assert result["observations"][0]["evidence"] in answer
    assert "omitted" in result["note"]
    assert "score" not in result


def test_feedback_rejects_wrong_types_and_preserves_self_checks():
    lesson = build_learning_plan(PROFILE, JOB)["lessons"][0]
    answer = "I would inspect the Service selector and Pod labels before looking at readiness."
    for output in ('[]', '{"observations": 8}', 'not JSON'):
        result = review_practice_answer(LlamaEngine(complete_fn=lambda _: output), lesson, answer)
        assert result["generated"] is False
        assert result["observations"] == []
        assert "self-checks" in result["note"]


def test_qualitative_outcomes_need_evidence_too():
    result = review_cover_letter("I wrote a Python tool that improved data accuracy and freed up people for higher-value tasks. This work matches the validation in the role.\n\nTaylor", PROFILE, JOB)
    assert any("improved data accuracy" in issue for issue in result["issues"])


def test_model_json_is_not_accepted_as_a_plain_text_letter():
    result = review_cover_letter(json.dumps({"letter": "Python work is relevant to this role. " * 10}), PROFILE, JOB)
    assert result["issues"]
