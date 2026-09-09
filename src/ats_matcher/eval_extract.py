from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ats_matcher.config import get_settings
from ats_matcher.extract.rules import preextract
from ats_matcher.llm.engine import ExtractionError, LlamaEngine
from ats_matcher.llm.merge import merge_extract
from ats_matcher.schemas.cv import CvExtract

DEFAULT_GOLDEN = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "golden" / "cvs.jsonl"


@dataclass
class EvalScores:
    n: int = 0
    valid_json: int = 0
    name_ok: int = 0
    name_n: int = 0
    skills_at_5: list[float] = field(default_factory=list)
    years_ok: int = 0
    years_n: int = 0
    github_ok: int = 0
    github_n: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "valid_json_rate": _ratio(self.valid_json, self.n),
            "name_accuracy": _ratio(self.name_ok, self.name_n),
            "skills_at_5": sum(self.skills_at_5) / len(self.skills_at_5) if self.skills_at_5 else None,
            "years_within_1": _ratio(self.years_ok, self.years_n),
            "github_url_exact": _ratio(self.github_ok, self.github_n),
            "gates": {
                "valid_json_ge_0.90": _ratio(self.valid_json, self.n) >= 0.90 if self.n else False,
                "github_exact_ge_0.80": _ratio(self.github_ok, self.github_n) >= 0.80
                if self.github_n
                else True,
            },
            "errors": self.errors,
        }


def load_golden(path: Path = DEFAULT_GOLDEN) -> list[dict[str, Any]]:
    if path.is_file():
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows
    try:
        from tests.fixtures.golden.cases import GOLDEN

        return GOLDEN
    except ImportError as exc:
        raise FileNotFoundError(path) from exc


def evaluate(
    engine: LlamaEngine,
    rows: list[dict[str, Any]] | None = None,
    include_age: bool = False,
) -> EvalScores:
    rows = rows or load_golden()
    scores = EvalScores()
    for row in rows:
        scores.n += 1
        expected = row["expected"]
        hints = preextract(row["text"])
        try:
            pred = engine.extract(row["text"], hints, include_age=include_age)
        except ExtractionError as exc:
            scores.errors.append(f"{row.get('id')}: {exc}")
            continue
        scores.valid_json += 1
        _score_row(scores, expected, pred)
    return scores


def evaluate_predictions(rows: list[tuple[dict[str, Any], CvExtract]]) -> EvalScores:
    """Offline scoring for unit tests (no model)."""
    scores = EvalScores()
    for row, pred in rows:
        scores.n += 1
        scores.valid_json += 1
        _score_row(scores, row["expected"], pred)
    return scores


def _score_row(scores: EvalScores, expected: dict[str, Any], pred: CvExtract) -> None:
    if expected.get("full_name"):
        scores.name_n += 1
        if _norm_name(pred.full_name) == _norm_name(expected["full_name"]):
            scores.name_ok += 1
    exp_skills = expected.get("skills") or []
    if exp_skills:
        scores.skills_at_5.append(_skills_at_k(exp_skills, pred.skills, k=5))
    if expected.get("years_experience") is not None:
        scores.years_n += 1
        if pred.years_experience is not None and abs(pred.years_experience - expected["years_experience"]) <= 1:
            scores.years_ok += 1
    if expected.get("github_url"):
        scores.github_n += 1
        if _norm_url(pred.github_url) == _norm_url(expected["github_url"]):
            scores.github_ok += 1


def score_merged_row(text: str, expected: dict[str, Any], raw_model: dict[str, Any]) -> CvExtract:
    hints = preextract(text)
    return merge_extract(CvExtract.model_validate(raw_model), hints)


def _skills_at_k(expected: list[str], actual: list[str], k: int = 5) -> float:
    exp = [s.lower() for s in expected[:k]]
    act = {s.lower() for s in actual}
    if not exp:
        return 1.0
    return sum(1 for s in exp if any(s == a or s in a or a in s for a in act)) / len(exp)


def _norm_name(value: str | None) -> str:
    return " ".join((value or "").lower().split())


def _norm_url(value: str | None) -> str:
    return (value or "").rstrip("/").lower()


def _ratio(num: int, den: int) -> float:
    return num / den if den else 0.0


def main() -> None:
    settings = get_settings()
    if not settings.llama_model_path:
        raise SystemExit("Set LLAMA_MODEL_PATH to run the golden-set eval.")
    engine = LlamaEngine(settings.llama_model_path, n_ctx=settings.llama_n_ctx, n_gpu_layers=settings.llama_n_gpu_layers)
    scores = evaluate(engine)
    print(json.dumps(scores.as_dict(), indent=2))
    gates = scores.as_dict()["gates"]
    if not all(gates.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
