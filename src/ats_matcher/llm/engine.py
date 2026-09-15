from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ats_matcher.extract.rules import RuleHints
from ats_matcher.llm.merge import merge_extract, normalize_strings
from ats_matcher.llm.prompts import (
    build_extract_messages,
    build_repair_messages,
    build_titles_messages,
    build_titles_repair_messages,
    truncate_for_llm,
)
from ats_matcher.schemas.cv import (
    CvExtract,
    PossibleTitles,
    cv_extract_llm_schema,
    possible_titles_llm_schema,
)

CompleteFn = Callable[[list[dict[str, str]]], str]


class ExtractionError(RuntimeError):
    pass


class LlamaEngine:
    """Constrained JSON extraction via llama-cpp-python (or an injected completer)."""

    def __init__(
        self,
        model_path: str | Path | None = None,
        *,
        n_ctx: int = 8192,
        n_gpu_layers: int = 0,
        complete_fn: CompleteFn | None = None,
        verbose: bool = False,
    ) -> None:
        self.model_path = Path(model_path) if model_path else None
        self.n_ctx = n_ctx
        self.n_gpu_layers = n_gpu_layers
        self.verbose = verbose
        self._complete = complete_fn
        self._llm: Any = None
        self._grammar: Any = None
        self._titles_grammar: Any = None
        self._disable_thinking = bool(self.model_path and "qwen3" in self.model_path.name.lower())
        if complete_fn is None:
            self._load()

    def _load(self) -> None:
        if self.model_path is None or not self.model_path.is_file():
            raise ExtractionError(
                "No GGUF model found. Set LLAMA_MODEL_PATH or pass --model, "
                "or use --rules-only. See README for download instructions."
            )
        try:
            from llama_cpp import Llama, LlamaGrammar
        except ImportError as exc:
            raise ExtractionError(
                "llama-cpp-python is not installed. On Windows do not use "
                "`pip install -e '.[llm]'` (that builds from source). Run: "
                "ats-match setup-llm --backend cpu"
            ) from exc

        self._grammar = LlamaGrammar.from_json_schema(json.dumps(cv_extract_llm_schema()))
        self._titles_grammar = LlamaGrammar.from_json_schema(json.dumps(possible_titles_llm_schema()))
        self._llm = Llama(
            model_path=str(self.model_path),
            n_ctx=self.n_ctx,
            n_gpu_layers=self.n_gpu_layers,
            chat_format=_infer_chat_format(self.model_path),
            verbose=self.verbose,
        )

    def extract(self, cv_text: str, hints: RuleHints, include_age: bool = False) -> CvExtract:
        text, _truncated = truncate_for_llm(cv_text)
        messages = build_extract_messages(text, hints)
        raw = self.complete(messages)
        parsed, problems = _try_parse(raw)
        if parsed is None or problems:
            repair = build_repair_messages(text, hints, raw, problems or ["invalid JSON"])
            raw = self.complete(repair)
            parsed, problems = _try_parse(raw)
        if parsed is None:
            raise ExtractionError(f"Model did not return valid CvExtract JSON: {problems}")
        profile = merge_extract(parsed, hints, include_age=include_age)
        titles = self._infer_titles(profile)
        return profile.model_copy(update={"possible_titles": titles})

    def _infer_titles(self, profile: CvExtract) -> list[str]:
        messages = build_titles_messages(profile)
        raw = self.complete(messages, grammar=self._titles_grammar, max_tokens=256)
        titles, problems = _try_parse_titles(raw)
        if titles is None or problems:
            repair = build_titles_repair_messages(profile, raw, problems or ["invalid JSON"])
            raw = self.complete(repair, grammar=self._titles_grammar, max_tokens=256)
            titles, _problems = _try_parse_titles(raw)
        cleaned = normalize_strings(titles or [], limit=8)
        if profile.certifications and _titles_ignore_certs(cleaned, profile):
            repair = build_titles_repair_messages(
                profile,
                json.dumps({"possible_titles": cleaned}),
                ["possible_titles only restates recent_titles; certifications were ignored"],
            )
            raw = self.complete(repair, grammar=self._titles_grammar, max_tokens=256)
            titles, _problems = _try_parse_titles(raw)
            cleaned = normalize_strings(titles or cleaned, limit=8)
        return cleaned

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        grammar: Any = None,
        max_tokens: int = 1536,
        temperature: float = 0.0,
        constrained: bool = True,
    ) -> str:
        if self._complete is not None:
            return self._complete(messages)
        assert self._llm is not None
        chosen = None
        if constrained:
            chosen = self._grammar if grammar is None else grammar
        elif grammar is not None:
            chosen = grammar
        outgoing = _with_no_think(messages) if self._disable_thinking else messages
        options: dict[str, Any] = {
            "messages": outgoing,
            "temperature": temperature,
            "top_p": 0.92 if temperature else 1.0,
            "max_tokens": max_tokens,
        }
        if chosen is not None:
            options["grammar"] = chosen
        result = self._llm.create_chat_completion(**options)
        return _strip_think(result["choices"][0]["message"]["content"] or "")


def _try_parse(raw: str) -> tuple[CvExtract | None, list[str]]:
    problems: list[str] = []
    payload = _strip_fences(raw)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        return None, [f"json: {exc}"]
    try:
        model = CvExtract.model_validate(data)
    except Exception as exc:
        return None, [f"schema: {exc}"]
    if not (model.full_name and model.full_name.strip()):
        problems.append("missing full_name")
    if problems:
        return model, problems
    return model, []


def _titles_ignore_certs(titles: list[str], profile: CvExtract) -> bool:
    """True when certifications exist but every title is just a restated recent title."""
    if not profile.certifications or not titles:
        return False
    recent = [t.lower() for t in profile.recent_titles]
    if not recent:
        return False

    def restates_recent(title: str) -> bool:
        low = title.lower()
        return any(low == r or low in r or r in low for r in recent)

    return all(restates_recent(title) for title in titles)


def _try_parse_titles(raw: str) -> tuple[list[str] | None, list[str]]:
    payload = _strip_fences(raw)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        return None, [f"json: {exc}"]
    try:
        model = PossibleTitles.model_validate(data)
    except Exception as exc:
        return None, [f"schema: {exc}"]
    if not model.possible_titles:
        return model.possible_titles, ["missing possible_titles"]
    return model.possible_titles, []


def _strip_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text[: -3]
        text = text.strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def _strip_think(raw: str) -> str:
    return re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()


def _with_no_think(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    copied = [dict(item) for item in messages]
    for item in reversed(copied):
        if item.get("role") != "user":
            continue
        content = str(item.get("content") or "")
        if "/no_think" not in content:
            item["content"] = content.rstrip() + "\n/no_think"
        break
    return copied


def _infer_chat_format(path: Path) -> str:
    name = path.name.lower()
    if "llama-3" in name or "llama3" in name:
        return "llama-3"
    return "chatml"
