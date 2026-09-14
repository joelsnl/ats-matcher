from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from ats_matcher import __version__
from ats_matcher.pipeline import parse_cv, match_jobs
from ats_matcher.jobs.service import JobSearchService
from ats_matcher.schemas.jobs import JobSearchQuery
from ats_matcher.schemas.profile import EnrichedProfile
from pydantic import ValidationError

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
    """GitHub enrichment is not implemented."""
    typer.echo("GitHub enrichment is not implemented.")
    raise typer.Exit(code=1)


@app.command()
def serve(
    port: int = typer.Option(8765, "--port"),
    model: Optional[Path] = typer.Option(None, "--model", help="Local GGUF model."),
    mode: str = typer.Option("cpu", "--mode", help="cpu, gpu, or basic."),
) -> None:
    """Run the localhost browser app (loopback only)."""
    from ats_matcher.llm.engine import ExtractionError
    from ats_matcher.server import MODES, launch

    if mode not in MODES:
        raise typer.BadParameter(f"Unknown mode {mode!r}. Choose cpu, gpu, or basic.")
    try:
        launch(port=port, model=model, mode=mode)
    except (ValueError, OSError, ExtractionError) as exc:
        raise typer.BadParameter(str(exc)) from exc


def _write_search(payload: dict, out: Optional[Path], status: str) -> None:
    encoded = json.dumps(payload, indent=2, ensure_ascii=False)
    if out:
        out.write_text(encoded + "\n", encoding="utf-8")
        typer.echo(f"Wrote {out}")
    else:
        typer.echo(encoded)
    if status == "error":
        raise typer.Exit(code=1)
    if status == "partial":
        raise typer.Exit(code=2)


def _providers(value: Optional[str]) -> list[str] | None:
    return value.split(",") if value is not None else None


@app.command()
def search(
    keyword: str = typer.Option(..., "--keyword", help="Job title or search terms. Only this query and filters are sent to the provider."),
    location: Optional[str] = typer.Option(None, "--location"),
    provider: Optional[str] = typer.Option(None, "--provider", help="Comma-separated source names. Defaults to JOBS_PROVIDER."),
    limit: int = typer.Option(15, "--limit", min=1, max=100),
    page: int = typer.Option(0, "--page", min=0, max=1000),
    date: str = typer.Option("past_week", "--date", help="any, past_month, past_week, 24hr (or 24h)"),
    days: Optional[int] = typer.Option(None, "--days", min=1, max=365, help="Posted within this many days; overrides --date."),
    job_type: Optional[str] = typer.Option(None, "--job-type", help="One type or comma-separated types, e.g. part_time,internship."),
    workplace: Optional[str] = typer.Option(None, "--workplace", help="on_site, remote, hybrid; combine with commas, e.g. remote,hybrid."),
    salary: Optional[int] = typer.Option(None, "--salary", help="LinkedIn salary band: 40000, 60000, 80000, 100000, 120000. Availability varies by market."),
    experience: Optional[str] = typer.Option(None, "--experience", help="One level or comma-separated levels, e.g. entry_level,associate."),
    sort: str = typer.Option("relevant", "--sort", help="relevant or recent"),
    verified: bool = typer.Option(False, "--verified"),
    under_10_applicants: bool = typer.Option(False, "--under-10-applicants"),
    translate_to: str = typer.Option("en", "--translate-to", help="Language for non-English job descriptions. Default: English."),
    no_translate: bool = typer.Option(False, "--no-translate", help="Keep original job descriptions."),
    out: Optional[Path] = typer.Option(None, "--out"),
) -> None:
    """Search real job sources without uploading a CV."""
    try:
        query = JobSearchQuery(keywords=keyword, location=location, limit=limit, page=page, date_since_posted=date, posted_within_days=days, job_type=job_type, workplace_type=workplace, salary=salary, experience_level=experience, sort_by=sort, has_verification=verified, under_10_applicants=under_10_applicants)
        result = JobSearchService().search(query, _providers(provider), translate_to=None if no_translate else translate_to, translate=not no_translate)
    except (ValueError, ValidationError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    _write_search(result.model_dump(mode="json"), out, result.jobs_meta.status)


@app.command()
def providers() -> None:
    """List implemented search channels."""
    typer.echo(json.dumps(JobSearchService().registry.list(), indent=2))


@app.command()
def match(
    profile: Path = typer.Option(..., "--profile", exists=True, help="Parsed or enriched profile JSON."),
    jobs: int = typer.Option(15, "--jobs", min=1, max=100),
    keyword: Optional[str] = typer.Option(None, "--keyword", help="Override inferred titles; required for a basic profile without titles."),
    location: Optional[str] = typer.Option(None, "--location"),
    provider: Optional[str] = typer.Option(None, "--provider"),
    translate_to: str = typer.Option("en", "--translate-to", help="Language for non-English job descriptions. Default: English."),
    no_translate: bool = typer.Option(False, "--no-translate", help="Keep original job descriptions."),
    out: Optional[Path] = typer.Option(None, "--out"),
) -> None:
    """Search from a CV profile. GitHub enrichment is not implemented."""
    try:
        raw = json.loads(profile.read_text(encoding="utf-8"))
        raw = raw.get("user_profile", raw)
        if not isinstance(raw, dict):
            raise ValueError("Expected a parsed profile object.")
        parsed = EnrichedProfile.model_validate({k: v for k, v in raw.items() if k in EnrichedProfile.model_fields})
        report = match_jobs(parsed, jobs, keywords=keyword, location=location, providers=_providers(provider), source_cv=str(profile), translate_to=None if no_translate else translate_to, translate=not no_translate)
    except (ValueError, OSError, AttributeError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    payload = report.model_dump(mode="json")
    payload["user_profile"] = report.user_profile.public_dump()
    _write_search(payload, out, report.jobs_meta.status)


@app.command()
def run(
    cv: Path = typer.Option(..., "--cv", exists=True, readable=True),
    out: Optional[Path] = typer.Option(None, "--out"),
    jobs: int = typer.Option(15, "--jobs", min=1, max=100),
    location: Optional[str] = typer.Option(None, "--location"),
    keyword: Optional[str] = typer.Option(None, "--keyword"),
    provider: Optional[str] = typer.Option(None, "--provider"),
    model: Optional[Path] = typer.Option(None, "--model"),
    rules_only: bool = typer.Option(False, "--rules-only"),
    include_age: bool = typer.Option(False, "--include-age"),
    translate_to: str = typer.Option("en", "--translate-to", help="Language for non-English job descriptions. Default: English."),
    no_translate: bool = typer.Option(False, "--no-translate", help="Keep original job descriptions."),
) -> None:
    """Read a CV and search live jobs using its titles or an explicit keyword."""
    profile, document = parse_cv(cv, model_path=model, rules_only=rules_only, include_age=include_age)
    typer.echo(f"parse: ok ({document.source}, {document.char_count} chars, quality={document.quality})", err=True)
    try:
        report = match_jobs(profile, jobs, keywords=keyword, location=location, providers=_providers(provider), source_cv=str(cv), translate_to=None if no_translate else translate_to, translate=not no_translate)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    payload = report.model_dump(mode="json")
    payload["user_profile"] = report.user_profile.public_dump(include_age=include_age)
    _write_search(payload, out, report.jobs_meta.status)


@app.command("setup-llm")
def setup_llm(
    backend: str = typer.Option(
        "cpu",
        "--backend",
        help="Prebuilt wheel: cpu (default), vulkan (Windows GPU), or cuda (cu124).",
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
