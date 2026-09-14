from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from ats_matcher.cli import app
from ats_matcher.pipeline import parse_cv

runner = CliRunner()


def test_parse_rules_only_txt(tmp_path: Path):
    cv = tmp_path / "cv.txt"
    cv.write_text(
        "Maya Chen\nmaya.chen@example.com\nhttps://github.com/maya-chen\n2018 - Present\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["parse", "--cv", str(cv), "--rules-only"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["email"] == "maya.chen@example.com"
    assert payload["github_url"] == "https://github.com/maya-chen"
    assert payload["_meta"]["rules_only"] is True
    assert "birth_year" not in payload


def test_parse_writes_out(tmp_path: Path):
    cv = tmp_path / "cv.txt"
    out = tmp_path / "cv.json"
    cv.write_text("a@b.co https://github.com/abc\n", encoding="utf-8")
    result = runner.invoke(app, ["parse", "--cv", str(cv), "--rules-only", "--out", str(out)])
    assert result.exit_code == 0
    assert out.is_file()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["github_url"] == "https://github.com/abc"


def test_enrich_is_stub_and_match_validates_profile():
    dummy = Path("pyproject.toml")
    result = runner.invoke(app, ["enrich", "--profile", str(dummy)])
    assert result.exit_code == 1
    assert "not implemented" in result.output.lower()
    assert runner.invoke(app, ["match", "--profile", str(dummy)]).exit_code == 2


def test_serve_help_is_available():
    help_text = runner.invoke(app, ["--help"]).output
    assert "serve" in help_text
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    assert "localhost" in result.output.lower()


def test_basic_run_requires_search_keywords(tmp_path: Path):
    cv = tmp_path / "cv.txt"
    cv.write_text("Pat Lee pat.lee@example.com\n", encoding="utf-8")
    result = runner.invoke(app, ["run", "--cv", str(cv), "--rules-only"])
    assert result.exit_code == 2
    assert "keyword" in result.output


def test_pipeline_parse_rules_only(tmp_path: Path):
    cv = tmp_path / "cv.txt"
    cv.write_text("https://github.com/zzz nina@example.com\n", encoding="utf-8")
    profile, doc = parse_cv(cv, rules_only=True)
    assert profile.github_url == "https://github.com/zzz"
    assert doc.source == "txt"
