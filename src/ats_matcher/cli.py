from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from ats_matcher import __version__
from ats_matcher.pipeline import parse_cv

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Local ATS CV parser and job matcher.")


@app.callback()
def _version(
    version: bool = typer.Option(False, "--version", help="Show version and exit."),
) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit()


@app.command()
def parse(
    cv: Path = typer.Option(..., "--cv", exists=True, readable=True, help="CV file (pdf, docx, txt)."),
    out: Optional[Path] = typer.Option(None, "--out", help="Write CvExtract JSON here."),
    model: Optional[Path] = typer.Option(None, "--model", help="Path to a GGUF model."),
    rules_only: bool = typer.Option(False, "--rules-only", help="Skip llama.cpp; regex fields only."),
    include_age: bool = typer.Option(False, "--include-age", help="Keep explicit age/birth year."),
    n_gpu_layers: Optional[int] = typer.Option(None, "--n-gpu-layers", help="llama.cpp GPU layers (-1 all, 0 CPU)."),
) -> None:
    """Extract structured CV JSON (text + regex + local LLM)."""
    profile, document = parse_cv(
        cv,
        model_path=model,
        rules_only=rules_only,
        include_age=include_age,
        n_gpu_layers=n_gpu_layers,
    )
    payload = profile.public_dump(include_age=include_age)
    payload["_meta"] = {
        "source": document.source,
        "quality": document.quality,
        "char_count": document.char_count,
        "rules_only": rules_only,
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if out:
        out.write_text(text + "\n", encoding="utf-8")
        typer.echo(f"Wrote {out}")
    else:
        typer.echo(text)


@app.command()
def enrich(
    profile: Path = typer.Option(..., "--profile", exists=True, help="CvExtract JSON from `parse`."),
) -> None:
    """Enrich a parsed CV with GitHub data (Phase 3)."""
    typer.echo("Not implemented (Phase 3: GitHub enrichment).")
    raise typer.Exit(code=1)


@app.command()
def match(
    profile: Path = typer.Option(..., "--profile", exists=True, help="Enriched profile JSON."),
    jobs: int = typer.Option(15, "--jobs", min=10, max=20),
) -> None:
    """Fetch live job listings (Phase 5)."""
    typer.echo("Not implemented (Phase 5: LinkedIn / job provider).")
    raise typer.Exit(code=1)


@app.command()
def run(
    cv: Path = typer.Option(..., "--cv", exists=True, readable=True),
    out: Optional[Path] = typer.Option(None, "--out"),
    jobs: int = typer.Option(15, "--jobs", min=10, max=20),
    location: Optional[str] = typer.Option(None, "--location"),
    model: Optional[Path] = typer.Option(None, "--model"),
    rules_only: bool = typer.Option(False, "--rules-only"),
    include_age: bool = typer.Option(False, "--include-age"),
) -> None:
    """Run the full pipeline. Phases 3–5 are not implemented yet."""
    profile, document = parse_cv(
        cv,
        model_path=model,
        rules_only=rules_only,
        include_age=include_age,
    )
    typer.echo(f"parse: ok ({document.source}, {document.char_count} chars, quality={document.quality})")
    typer.echo("enrich: not implemented (Phase 3)")
    typer.echo("match: not implemented (Phase 5)")
    payload = {
        "user_profile": profile.public_dump(include_age=include_age),
        "jobs": [],
        "jobs_meta": {
            "requested": jobs,
            "returned": 0,
            "provider": "not_implemented",
            "errors": ["Phases 3–5 not implemented"],
            "location_override": location,
        },
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if out:
        out.write_text(text + "\n", encoding="utf-8")
        typer.echo(f"Wrote partial report {out}")
    else:
        typer.echo(text)
    raise typer.Exit(code=2)


@app.command("setup-llm")
def setup_llm(
    backend: str = typer.Option(
        "vulkan",
        "--backend",
        help="Prebuilt wheel: vulkan (Windows GPU), cpu, or cuda (cu124).",
    ),
) -> None:
    """Install a prebuilt llama-cpp-python wheel (avoids compiling from source)."""
    from ats_matcher.llm.install import WHEEL_INDEXES, install_llama_cpp

    if backend not in WHEEL_INDEXES:
        typer.echo(f"Unknown backend {backend!r}. Choose: {', '.join(WHEEL_INDEXES)}")
        raise typer.Exit(code=1)
    typer.echo(f"Installing llama-cpp-python ({backend} wheel, no compiler)...")
    try:
        install_llama_cpp(backend)
    except Exception as exc:
        typer.echo(f"Install failed: {exc}")
        raise typer.Exit(code=1)
    typer.echo("Done. Next: download a GGUF and set LLAMA_MODEL_PATH (see README).")


if __name__ == "__main__":
    app()
