# ATS Matcher

Local CLI that parses a CV with **llama.cpp**, extracts a structured profile, and (later phases) matches live job listings. Phases 0–2 are implemented: package scaffold, text extraction, and constrained JSON extraction.

The language model never invents job URLs. Age / birth year is omitted from output unless you pass `--include-age` and the CV states it explicitly.

## Requirements

- Python 3.11+
- A GGUF instruct model for `parse` (optional for `--rules-only`)

## Install

```bash
cd ats-matcher
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -e ".[dev]"
```

### Local LLM (`llama-cpp-python`)

`pip install -e ".[llm]"` downloads a **source tarball** and tries to compile. That fails on Windows unless Visual Studio C++ tools are installed.

Use a **prebuilt wheel** instead (no compiler):

```powershell
# RTX / AMD / Intel GPU on Windows (Vulkan) — recommended
ats-match setup-llm --backend vulkan

# CPU only
ats-match setup-llm --backend cpu
```

Equivalent pip:

```powershell
pip install --only-binary=:all: --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/vulkan llama-cpp-python==0.3.35
```

`--only-binary=:all:` is important: without it, pip may still fall back to compiling from PyPI.

## Download a model

Recommended default: **Qwen2.5-7B-Instruct** Q4_K_M (~4.7 GB).

The official `Qwen/Qwen2.5-7B-Instruct-GGUF` repo splits Q4_K_M into two shards, so `qwen2.5-7b-instruct-q4_k_m.gguf` does not exist. Use a single-file community quant:

```powershell
hf download bartowski/Qwen2.5-7B-Instruct-GGUF Qwen2.5-7B-Instruct-Q4_K_M.gguf --local-dir .models
```

Weaker machines: `Qwen2.5-7B-Instruct-Q3_K_M.gguf` from the same repo.

Then:

```powershell
$env:LLAMA_MODEL_PATH = "$PWD\.models\Qwen2.5-7B-Instruct-Q4_K_M.gguf"
```

or pass `--model` on the CLI.

## CLI

```bash
# Text + regex + local LLM → CvExtract JSON
ats-match parse --cv path\to\resume.pdf --out cv.json

# Same, but skip llama.cpp (regex/contact fields only)
ats-match parse --cv path\to\resume.pdf --rules-only --out cv.json

# Remaining stages (Phase 3+)
ats-match enrich --profile cv.json
ats-match match --profile enriched.json
ats-match run --cv path\to\resume.pdf --out report.json
```

## Tests

```bash
pytest
```

Golden-set LLM eval (requires `LLAMA_MODEL_PATH`):

```bash
pytest -m llm
# or
python -m ats_matcher.eval_extract
```

Gates: ≥90% valid JSON, ≥80% exact GitHub URL when the CV contains one.

## Project layout

```
src/ats_matcher/
  cli.py            Typer commands
  pipeline.py       parse / stubs for later stages
  extract/          PDF/DOCX text + regex pre-extract
  llm/              llama.cpp engine, prompts, merge
  schemas/          Pydantic + JSON Schema
  jobs/base.py      JobProvider protocol (stub)
grammars/           JSON Schema + GBNF for llama.cpp
tests/fixtures/     golden CVs and generated PDFs
```
