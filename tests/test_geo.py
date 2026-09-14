from ats_matcher.geo import enrich_location, format_search_location
from ats_matcher.llm.merge import merge_extract
from ats_matcher.extract.rules import preextract
from ats_matcher.schemas.cv import CvExtract, Location


def test_iso_country_code_becomes_city_and_country():
    location = Location(city="Amsterdam", country="NL", raw="Amsterdam, NL")
    assert format_search_location(location) == "Amsterdam, Netherlands"
    assert enrich_location(location).country == "Netherlands"


def test_known_city_fills_country_when_missing():
    assert format_search_location(Location(city="Amsterdam")) == "Amsterdam, Netherlands"
    assert format_search_location(Location(city="Berlin")) == "Berlin, Germany"


def test_ambiguous_or_empty_location_is_left_alone():
    assert format_search_location(Location(city="Springfield")) == "Springfield"
    assert format_search_location(Location()) is None
    assert format_search_location(Location(raw="Remote")) == "Remote"


def test_merge_expands_country_codes():
    hints = preextract("Joel joel@example.com")
    merged = merge_extract(
        CvExtract(full_name="Joel", location=Location(city="Amsterdam", country="NL")),
        hints,
    )
    assert merged.location.country == "Netherlands"
    assert format_search_location(merged.location) == "Amsterdam, Netherlands"
