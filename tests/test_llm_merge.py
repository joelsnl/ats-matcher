from __future__ import annotations

import json

from ats_matcher.eval_extract import evaluate_predictions
from ats_matcher.extract.rules import preextract
from ats_matcher.llm.engine import LlamaEngine
from ats_matcher.llm.merge import hints_to_cv, merge_extract
from ats_matcher.llm.prompts import build_extract_messages, build_titles_messages, truncate_for_llm
from ats_matcher.schemas.cv import CvExtract, Employer, SpokenLanguage
from tests.fixtures.golden.cases import GOLDEN


def test_rules_overwrite_hallucinated_identifiers():
    hints = preextract("Pat Lee pat.lee@example.com https://github.com/patlee")
    model = CvExtract(
        full_name="Pat Lee",
        email="wrong@example.com",
        github_url="https://github.com/hallucinated",
        skills=["Python"],
        confidence=0.4,
    )
    merged = merge_extract(model, hints)
    assert merged.email == "pat.lee@example.com"
    assert merged.github_url == "https://github.com/patlee"


def test_age_stripped_without_flag():
    hints = preextract("Sam Sam@example.com Born 1990")
    model = CvExtract(
        full_name="Sam",
        birth_year=1990,
        age_estimate=36,
        age_source="explicit_cv",
        skills=["Excel"],
    )
    merged = merge_extract(model, hints, include_age=False)
    assert merged.birth_year is None
    kept = merge_extract(model, hints, include_age=True)
    assert kept.birth_year == 1990


def test_possible_titles_are_deduped():
    hints = preextract("Pat Lee pat.lee@example.com")
    model = CvExtract(
        full_name="Pat Lee",
        possible_titles=["Backend Engineer", "backend engineer", "Software Engineer", ""],
        confidence=0.5,
    )
    merged = merge_extract(model, hints)
    assert merged.possible_titles == ["Backend Engineer", "Software Engineer"]


def test_employers_and_certifications_are_deduped():
    hints = preextract("Pat Lee pat.lee@example.com")
    model = CvExtract(
        full_name="Pat Lee",
        employers=["Nordwind Labs", "nordwind labs", "Helio Systems", ""],
        certifications=["AWS SAA", "aws saa", "CKA"],
        confidence=0.5,
    )
    merged = merge_extract(model, hints)
    assert merged.employers == [
        Employer(name="Nordwind Labs", client=None),
        Employer(name="Helio Systems", client=None),
    ]
    assert merged.certifications == ["AWS SAA", "CKA"]


def test_spoken_languages_parse_levels_and_dedupe():
    hints = preextract("Pat pat@example.com")
    model = CvExtract(
        full_name="Pat",
        spoken_languages=["English (Native)", "english", "Dutch — A2", "French"],
        confidence=0.5,
    )
    merged = merge_extract(model, hints)
    assert merged.spoken_languages == [
        SpokenLanguage(name="English", level="Native"),
        SpokenLanguage(name="Dutch", level="A2"),
        SpokenLanguage(name="French", level=None),
    ]
    assert merged.public_dump()["spoken_languages"] == [
        {"name": "English", "level": "Native"},
        {"name": "Dutch", "level": "A2"},
        {"name": "French"},
    ]


def test_employer_client_split_from_brackets():
    hints = preextract("Joel joelsnl@hotmail.com")
    model = CvExtract(
        full_name="Joel",
        employers=[
            "Accenture (Client: ASML)",
            {"name": "Dizain-Sync B.V.", "client": "ASML"},
            {"name": "YER (Client: ASML)", "client": None},
        ],
        confidence=0.9,
    )
    merged = merge_extract(model, hints)
    assert merged.employers == [
        Employer(name="Accenture", client="ASML"),
        Employer(name="Dizain-Sync B.V.", client="ASML"),
        Employer(name="YER", client="ASML"),
    ]
    assert merged.public_dump()["employers"] == [
        {"name": "Accenture", "client": "ASML"},
        {"name": "Dizain-Sync B.V.", "client": "ASML"},
        {"name": "YER", "client": "ASML"},
    ]


def test_parenthetical_location_is_not_a_client():
    hints = preextract("Pat pat@example.com")
    model = CvExtract(
        full_name="Pat",
        employers=["Microsoft (Redmond)", "IBM (NY)", "Google (YouTube)"],
        confidence=0.5,
    )
    merged = merge_extract(model, hints)
    assert [e.model_dump() for e in merged.employers] == [
        {"name": "Microsoft (Redmond)", "client": None},
        {"name": "IBM (NY)", "client": None},
        {"name": "Google (YouTube)", "client": None},
    ]
    assert all("client" not in row for row in merged.public_dump()["employers"])


def test_skills_compact_duplicates_are_merged():
    hints = preextract("Pat pat@example.com")
    model = CvExtract(
        full_name="Pat",
        skills=["Platform Engineering", "PlatformEngineering", "JavaScript", "java script"],
        confidence=0.5,
    )
    merged = merge_extract(model, hints)
    assert merged.skills == ["Platform Engineering", "JavaScript"]
    assert "java script" not in merged.skills


def test_hints_to_cv_fills_contact_only():
    hints = preextract("a@b.co https://github.com/abc")
    profile = hints_to_cv(hints)
    assert profile.email == "a@b.co"
    assert profile.github_url == "https://github.com/abc"
    assert profile.full_name is None
    assert profile.skills == []


def test_engine_repair_then_merge():
    calls = {"n": 0}

    def complete(messages):
        calls["n"] += 1
        user = messages[-1]["content"]
        if "Extracted profile" in user:
            return json.dumps({"possible_titles": ["Backend Engineer", "Software Engineer"]})
        if calls["n"] == 1:
            return "not json"
        return json.dumps(
            {
                "full_name": "Maya Chen",
                "email": None,
                "skills": ["Python", "FastAPI"],
                "years_experience": 6,
                "primary_industry": "software",
                "location": {"city": "Berlin", "region": None, "country": "Germany", "raw": "Berlin"},
                "github_url": None,
                "linkedin_url": None,
                "recent_titles": ["Senior Backend Engineer"],
                "employers": [
                    {"name": "Nordwind Labs", "client": None},
                    {"name": "Helio Systems", "client": None},
                ],
                "certifications": ["AWS SAA"],
                "spoken_languages": [{"name": "German", "level": "C1"}],
                "birth_year": None,
                "age_estimate": None,
                "age_source": None,
                "confidence": 0.7,
            }
        )

    engine = LlamaEngine(complete_fn=complete)
    text = GOLDEN[0]["text"]
    pred = engine.extract(text, preextract(text))
    assert calls["n"] == 3
    assert pred.full_name == "Maya Chen"
    assert pred.github_url == "https://github.com/maya-chen"
    assert pred.email == "maya.chen@example.com"
    assert pred.employers == [
        Employer(name="Nordwind Labs", client=None),
        Employer(name="Helio Systems", client=None),
    ]
    assert pred.certifications == ["AWS SAA"]
    assert pred.spoken_languages == [SpokenLanguage(name="German", level="C1")]
    assert pred.possible_titles == ["Backend Engineer", "Software Engineer"]
    dumped = pred.public_dump()
    assert dumped["employers"] == [
        {"name": "Nordwind Labs"},
        {"name": "Helio Systems"},
    ]


def test_offline_eval_gates_with_perfect_predictions():
    pairs = []
    for row in GOLDEN:
        expected = row["expected"]
        pred = merge_extract(
            CvExtract(
                full_name=expected.get("full_name"),
                skills=expected.get("skills") or [],
                years_experience=expected.get("years_experience"),
                github_url=expected.get("github_url"),
                email=expected.get("email"),
                confidence=1.0,
            ),
            preextract(row["text"]),
        )
        pairs.append((row, pred))
    scores = evaluate_predictions(pairs)
    report = scores.as_dict()
    assert report["valid_json_rate"] == 1.0
    assert report["gates"]["valid_json_ge_0.90"]
    assert report["gates"]["github_exact_ge_0.80"]
    assert report["github_url_exact"] == 1.0


def test_prompt_includes_hints():
    hints = preextract("x@y.com https://github.com/z")
    messages = build_extract_messages("hello", hints)
    assert messages[0]["role"] == "system"
    assert "known_github" in messages[1]["content"]
    assert "https://github.com/z" in messages[1]["content"]
    assert "employers" in messages[1]["content"]
    assert "spoken_languages" in messages[1]["content"]
    assert "client" in messages[0]["content"]
    assert "headline" not in messages[1]["content"]
    assert "possible_titles" not in messages[1]["content"]


def test_titles_prompt_uses_extracted_profile():
    profile = CvExtract(
        full_name="Maya Chen",
        skills=["Python"],
        recent_titles=["Senior Backend Engineer"],
        employers=[{"name": "Nordwind Labs", "client": "Helio Systems"}],
        certifications=["AWS SAA"],
        spoken_languages=[{"name": "German", "level": "C1"}],
        email="maya.chen@example.com",
        possible_titles=["should not appear"],
    )
    messages = build_titles_messages(profile)
    user = messages[1]["content"]
    assert "Extracted profile" in user
    assert "Nordwind Labs" in user
    assert "Helio Systems" in user
    assert '"client"' in user
    assert "AWS SAA" in user
    assert "German" in user
    assert "spoken_languages" in user
    assert "certifications" in user
    assert "Occupational certifications" in user
    assert "headline" not in messages[0]["content"]
    assert "maya.chen@example.com" not in user
    assert "should not appear" not in user


def test_truncate_for_llm():
    text, clipped = truncate_for_llm("a" * 100, max_chars=1000)
    assert clipped is False
    text, clipped = truncate_for_llm("a" * 50_000, max_chars=1000)
    assert clipped is True
    assert "omitted" in text
