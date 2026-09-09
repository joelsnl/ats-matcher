from __future__ import annotations

from ats_matcher.extract.rules import preextract

CONTACT_BLOCK = """
Alex Rivera
alex.rivera@example.com
+1 (415) 555-0102
https://github.com/arivera-dev
https://www.linkedin.com/in/alex-rivera
Experience: 2019 - 2022 and 2022 - Present
See also github.com/features/actions
"""


def test_preextract_email_github_linkedin():
    hints = preextract(CONTACT_BLOCK)
    assert hints.email == "alex.rivera@example.com"
    assert hints.github_url == "https://github.com/arivera-dev"
    assert hints.linkedin_url == "https://www.linkedin.com/in/alex-rivera"
    assert "features" not in hints.github_usernames


def test_preextract_phone_and_year_ranges():
    hints = preextract(CONTACT_BLOCK)
    assert hints.phones
    assert any(a == 2019 and b == 2022 for a, b in hints.year_ranges)
    assert any(a == 2022 and b is None for a, b in hints.year_ranges)


def test_preextract_bare_github_and_linkedin():
    text = "Contact github.com/foo-bar and linkedin.com/in/foo_bar"
    hints = preextract(text)
    assert hints.github_url == "https://github.com/foo-bar"
    assert hints.linkedin_url == "https://www.linkedin.com/in/foo_bar"


def test_short_numbers_are_not_phones():
    hints = preextract("Room 12 page 34 year 2020")
    assert hints.phones == []


def test_stated_years_experience_phrase():
    hints = preextract("Software engineer with 6 years building APIs. 2014 - 2018 B.Sc.")
    assert hints.stated_years_experience == 6.0
