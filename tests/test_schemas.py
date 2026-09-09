from __future__ import annotations

from ats_matcher.schemas.cv import (
    CvExtract,
    Location,
    cv_extract_llm_schema,
    possible_titles_llm_schema,
)


def test_cv_extract_defaults_and_public_dump_strips_age():
    profile = CvExtract(
        full_name="Ada Lovelace",
        skills=["math"],
        birth_year=1990,
        age_estimate=36,
        age_source="explicit_cv",
        confidence=0.8,
    )
    public = profile.public_dump(include_age=False)
    assert "birth_year" not in public
    assert "age_estimate" not in public
    kept = profile.public_dump(include_age=True)
    assert kept["birth_year"] == 1990
    assert kept["age_source"] == "explicit_cv"


def test_title_context_omits_contact_and_prior_titles():
    profile = CvExtract(
        full_name="Ada Lovelace",
        email="ada@example.com",
        skills=["math"],
        employers=[{"name": "Analytical Engine Co", "client": None}],
        certifications=["None"],
        spoken_languages=[{"name": "English", "level": "Native"}],
        possible_titles=["Mathematician"],
        confidence=0.8,
    )
    ctx = profile.title_context()
    assert list(ctx.keys())[0] == "skills"
    assert ctx["certifications"] == ["None"]
    assert ctx["spoken_languages"] == [{"name": "English", "level": "Native"}]
    assert ctx["employers"] == [{"name": "Analytical Engine Co"}]
    assert "email" not in ctx
    assert "full_name" not in ctx
    assert "possible_titles" not in ctx
    assert "confidence" not in ctx


def test_location_nested():
    profile = CvExtract(location=Location(city="Berlin", country="Germany", raw="Berlin, Germany"))
    assert profile.location.city == "Berlin"


def test_llm_schema_is_flat_and_closed():
    schema = cv_extract_llm_schema()
    assert schema["additionalProperties"] is False
    assert "$ref" not in str(schema)
    assert "full_name" in schema["properties"]
    assert "location" in schema["properties"]
    assert "employers" in schema["properties"]
    emp_item = schema["properties"]["employers"]["items"]
    assert emp_item["required"] == ["name"]
    assert "client" in emp_item["properties"]
    assert "certifications" in schema["properties"]
    assert "spoken_languages" in schema["properties"]
    lang_item = schema["properties"]["spoken_languages"]["items"]
    assert lang_item["required"] == ["name"]
    assert "level" in lang_item["properties"]
    assert "possible_titles" not in schema["properties"]
    assert schema["properties"]["location"]["additionalProperties"] is False
    titles = possible_titles_llm_schema()
    assert titles["additionalProperties"] is False
    assert titles["properties"]["possible_titles"]["maxItems"] == 8
