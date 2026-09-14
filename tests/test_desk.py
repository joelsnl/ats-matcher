import json

import pytest

from ats_matcher.llm.cover_letter import CoverLetterError, build_cover_letter_messages, revise_cover_passage
from ats_matcher.llm.role_context import build_role_context, writing_facts
from ats_matcher.llm.training import generate_practice_lesson

PROFILE = {"name": "Taylor", "skills": ["Python"], "achievements": "I wrote Python import checks."}
JOB = {"title": "Engineer", "company": "Example", "description": "Required: Python and SQL. Explain technical decisions to stakeholders."}
PASSAGE = "I wrote Python import checks and would like to discuss this work with your team."
LETTER = "Dear Example team,\n\n" + PASSAGE + "\n\nYour Engineer role involves validation work. I would welcome the chance to explain how I approached the import checks and learn about the team's requirements.\n\nTaylor"


class Engine:
    def __init__(self, output):
        self.output = output
        self.messages = None

    def complete(self, messages, **kwargs):
        self.messages = messages
        return self.output


def revise(output, **kwargs):
    start = LETTER.index(PASSAGE)
    return revise_cover_passage(Engine(output), PROFILE, JOB, LETTER, start, start + len(PASSAGE), "plain", **kwargs)


def test_revision_changes_only_the_requested_passage():
    replacement = "I wrote Python import checks. I would welcome a conversation about this work."
    result = revise(replacement)
    assert result["replacement"] == replacement
    assert "context" in result["review"]


@pytest.mark.parametrize("output", ["", "```json\n{}", "I managed AWS production systems for 42 years.", "x" * 2501])
def test_revision_rejects_empty_structured_oversized_or_new_unsupported_claims(output):
    with pytest.raises(CoverLetterError):
        revise(output)


@pytest.mark.parametrize("start,end,intent", [(True, 40, "plain"), (-1, 40, "plain"), (0, 5, "plain"), (0, 9999, "plain"), (0, 40, []), (0, 40, "invent")])
def test_revision_validates_offsets_and_fixed_edit_intents(start, end, intent):
    with pytest.raises(ValueError):
        revise_cover_passage(Engine("unused"), PROFILE, JOB, LETTER, start, end, intent)


def test_motivation_is_not_promoted_into_career_evidence():
    profile = {**PROFILE, "motivation": "I want to learn SQL and become a manager."}
    context = build_role_context(profile, JOB)
    assert next(r for r in context["requirements"] if r["name"] == "SQL")["status"] == "not_evidenced"
    assert "motivation" not in writing_facts(profile, context)
    messages = build_cover_letter_messages(profile, JOB)
    assert '"candidate_motivation": "I want to learn SQL' in messages[1]["content"]


def test_followup_generation_receives_bounded_learning_focus_and_keeps_fallback():
    context = build_role_context(PROFILE, JOB)
    skill = next(r["id"] for r in context["requirements"] if r["name"] == "SQL")
    engine = Engine("not json")
    lesson = generate_practice_lesson(engine, PROFILE, JOB, skill, focus="join totals " * 300)
    request = json.loads(engine.messages[1]["content"])
    assert len(request["previous_attempt_learning_focus"]) == 1200
    assert lesson["exercise"] and not lesson["generated"]


def test_logging_rephrasing_preserves_evidence_without_claiming_a_logging_platform():
    profile = {"achievements": "I checked required fields and logged invalid rows."}
    context = build_role_context(profile, {"description": "Required: Logging and Splunk."})
    rows = {r["name"]: r for r in context["requirements"]}
    assert rows["Logging"]["profile_evidence"] == profile["achievements"]
    assert rows["Splunk"]["status"] == "not_evidenced"
    for example in ("I never logged invalid rows.", "I am learning how files logged invalid rows.", "I logged gym hours."):
        row = build_role_context({"achievements": example}, {"description": "Required: Logging."})["requirements"][0]
        assert row["status"] == "not_evidenced"
