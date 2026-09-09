from __future__ import annotations

import os
from pathlib import Path

import pytest

from ats_matcher.eval_extract import evaluate
from ats_matcher.llm.engine import LlamaEngine
from tests.fixtures.golden.cases import GOLDEN

pytestmark = pytest.mark.llm


@pytest.fixture(scope="module")
def llm_engine() -> LlamaEngine:
    path = os.environ.get("LLAMA_MODEL_PATH")
    if not path or not Path(path).is_file():
        pytest.skip("LLAMA_MODEL_PATH is not set to a GGUF file")
    try:
        return LlamaEngine(path)
    except Exception as exc:
        pytest.skip(f"Could not load llama.cpp model: {exc}")


def test_golden_set_gates(llm_engine: LlamaEngine):
    scores = evaluate(llm_engine, GOLDEN)
    report = scores.as_dict()
    assert report["n"] == len(GOLDEN)
    assert report["valid_json_rate"] >= 0.90, report
    if report["github_url_exact"] is not None:
        assert report["gates"]["github_exact_ge_0.80"], report
