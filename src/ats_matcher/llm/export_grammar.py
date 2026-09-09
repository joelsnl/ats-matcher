from __future__ import annotations

import json
from pathlib import Path

from ats_matcher.schemas.cv import cv_extract_llm_schema, possible_titles_llm_schema

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "grammars" / "cv_extract.schema.json"
TITLES_SCHEMA_PATH = ROOT / "grammars" / "possible_titles.schema.json"
GBNF_PATH = ROOT / "grammars" / "cv_extract.gbnf"


def write_schema(path: Path = SCHEMA_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cv_extract_llm_schema(), indent=2) + "\n", encoding="utf-8")
    titles_path = TITLES_SCHEMA_PATH if path == SCHEMA_PATH else path.with_name("possible_titles.schema.json")
    titles_path.write_text(json.dumps(possible_titles_llm_schema(), indent=2) + "\n", encoding="utf-8")
    return path


def write_gbnf(path: Path = GBNF_PATH) -> Path:
    """Write GBNF from the JSON schema when llama-cpp-python is installed."""
    try:
        from llama_cpp import LlamaGrammar
    except ImportError:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_FALLBACK_GBNF, encoding="utf-8")
        return path

    grammar = LlamaGrammar.from_json_schema(json.dumps(cv_extract_llm_schema()))
    raw = getattr(grammar, "_grammar", None) or getattr(grammar, "grammar", None)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(raw, str) and raw.strip():
        path.write_text(raw if raw.endswith("\n") else raw + "\n", encoding="utf-8")
    else:
        path.write_text(_FALLBACK_GBNF, encoding="utf-8")
    return path


# Minimal JSON-object grammar so llama-cli can be used without llama-cpp-python.
_FALLBACK_GBNF = r"""
root   ::= object
object ::= "{" ws members? ws "}"
members ::= member (ws "," ws member)*
member ::= string ws ":" ws value
array  ::= "[" ws items? ws "]"
items  ::= value (ws "," ws value)*
value  ::= object | array | string | number | "true" | "false" | "null"
string ::= "\"" chars "\""
chars  ::= char*
char   ::= [^"\\\x00-\x1F] | "\\" escape
escape ::= ["\\/bfnrt] | "u" hex hex hex hex
hex    ::= [0-9a-fA-F]
number ::= "-"? digits frac? exp?
digits ::= [0-9]+
frac   ::= "." [0-9]+
exp    ::= [eE] [+\-]? [0-9]+
ws     ::= [ \t\n\r]*
"""


if __name__ == "__main__":
    print(write_schema())
    print(write_gbnf())
