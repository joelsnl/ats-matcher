"""Localhost HTTP app. Run with python -m ats_matcher.server or ats-match serve."""
from __future__ import annotations

import argparse
import json
import logging
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from ats_matcher.config import Settings, get_settings
from ats_matcher.jobs.service import JobSearchService
from ats_matcher.jobs.translate import GoogleTranslator, TranslationError, language_choices, language_label, normalize_language
from ats_matcher.llm.cover_letter import CoverLetterError, cover_options, generate_cover_letter, review_cover_letter, revise_cover_passage
from ats_matcher.llm.interview_prep import generate_interview_prep
from ats_matcher.llm.role_context import build_role_context
from ats_matcher.llm.training import generate_practice_lesson, review_practice_answer
from ats_matcher.llm.engine import ExtractionError, LlamaEngine
from ats_matcher.pipeline import parse_cv
from ats_matcher.schemas.jobs import JobSearchQuery
from pydantic import ValidationError

PARSE_PROFILE_FIELDS = (
    "full_name", "skills", "possible_titles", "recent_titles", "location",
    "years_experience", "primary_industry", "employers", "certifications",
)


def _clip(value: object, limit: int) -> str:
    return str(value).strip()[:limit] if isinstance(value, str) else ""


def _string_list(value: object, limit: int, item_limit: int = 80) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: dict[str, str] = {}
    for item in value:
        name = _clip(item, item_limit)
        if name:
            seen.setdefault(name.lower(), name)
        if len(seen) >= limit:
            break
    return list(seen.values())


def _employers(value: object) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not isinstance(value, list):
        return rows
    for item in value:
        if isinstance(item, str):
            name = _clip(item, 120)
            if name:
                rows.append({"name": name})
        elif isinstance(item, dict):
            name = _clip(item.get("name"), 120)
            if not name:
                continue
            client = _clip(item.get("client"), 120)
            rows.append({"name": name, **({"client": client} if client else {})})
        if len(rows) >= 15:
            break
    return rows


def _cover_letter_payload(payload: dict) -> tuple[dict, dict, int]:
    raw_profile = payload.get("profile")
    raw_job = payload.get("job")
    if not isinstance(raw_profile, dict) or not isinstance(raw_job, dict):
        raise ValueError("Include the profile and the job you want to write about.")
    name = _clip(raw_profile.get("name"), 80)
    title = _clip(raw_job.get("title"), 200)
    company = _clip(raw_job.get("company"), 200)
    description = _clip(raw_job.get("description"), 12000)
    if not name:
        raise ValueError("Add your name in your profile first.")
    if not title or not company:
        raise ValueError("This listing is missing a title or company.")
    if len(description) < 40:
        raise ValueError("Paste the job description so this can talk about this role.")
    refresh = payload.get("refresh") or 0
    if isinstance(refresh, bool) or not isinstance(refresh, int) or refresh < 0 or refresh > 50:
        raise ValueError("Try again.")
    years = raw_profile.get("years_experience")
    profile = {
        "name": name,
        "location": _clip(raw_profile.get("location"), 100),
        "mode": _clip(raw_profile.get("mode"), 20),
        "years_experience": years if not isinstance(years, bool) and isinstance(years, (int, float)) and 0 <= float(years) <= 60 else None,
        "roles": _string_list(raw_profile.get("roles"), 8),
        "recent_titles": _string_list(raw_profile.get("recent_titles"), 8),
        "skills": _string_list(raw_profile.get("skills"), 40),
        "employers": _employers(raw_profile.get("employers")),
        "certifications": _string_list(raw_profile.get("certifications"), 15, 120),
        "industry": _clip(raw_profile.get("industry"), 80),
        "note": _clip(raw_profile.get("note"), 2000),
        "cv_text": _clip(raw_profile.get("cv_text"), 12000),
        "achievements": _clip(raw_profile.get("achievements"), 3000),
        "motivation": _clip(raw_profile.get("motivation"), 800),
    }
    job = {
        "title": title,
        "company": company,
        "location": _clip(raw_job.get("location"), 200),
        "workplace_type": _clip(raw_job.get("workplace_type"), 40),
        "description": description,
        "language": _clip(raw_job.get("language"), 12) or "en",
    }
    return profile, job, refresh

REPO_ROOT = Path(__file__).resolve().parents[2]
ASSETS = REPO_ROOT / "app"
MAX_UPLOAD = 5 * 1024 * 1024
PARSE_TIMEOUT_BASIC = 30
PARSE_TIMEOUT_MODEL = 300
MODES = ("cpu", "gpu", "basic")
LOG = logging.getLogger(__name__)
NO_MODEL_HELP = (
    "A GGUF model is required. Download one into .models (see README), "
    "set LLAMA_MODEL_PATH, or pass --model. Use --mode basic to skip the model."
)


def discover_gguf(search_root: Path | None = None) -> Path | None:
    """Prefer a Q4_K_M file in .models, then any other .gguf in .models or models."""
    root = search_root or REPO_ROOT
    files: list[Path] = []
    for folder in (root / ".models", root / "models"):
        if folder.is_dir():
            files.extend(path for path in folder.glob("*.gguf") if path.is_file())
    if not files:
        return None
    return sorted(files, key=lambda path: (0 if "q4_k_m" in path.name.lower() else 1, path.name.lower()))[0]


def resolve_model(
    cli_model: Path | None = None,
    *,
    settings: Settings | None = None,
    search_root: Path | None = None,
) -> Path | None:
    """--model, else LLAMA_MODEL_PATH, else a GGUF in .models / models."""
    if cli_model is not None:
        return Path(cli_model)
    path = (settings or get_settings()).llama_model_path
    if path:
        return Path(path)
    return discover_gguf(search_root)


def gpu_layers_for_mode(mode: str, settings: Settings | None = None) -> int:
    """cpu always uses the CPU. gpu offloads all layers unless LLAMA_N_GPU_LAYERS is set."""
    if mode != "gpu":
        return 0
    settings = settings or get_settings()
    return settings.llama_n_gpu_layers if settings.llama_n_gpu_layers != 0 else -1


def create_engine(
    model: Path | None,
    settings: Settings | None = None,
    *,
    n_gpu_layers: int | None = None,
) -> LlamaEngine | None:
    if model is None:
        return None
    settings = settings or get_settings()
    layers = settings.llama_n_gpu_layers if n_gpu_layers is None else n_gpu_layers
    return LlamaEngine(
        model,
        n_ctx=settings.llama_n_ctx,
        n_gpu_layers=layers,
    )


def create_server(
    port: int = 8765,
    model: Path | None = None,
    job_service: JobSearchService | None = None,
    engine: LlamaEngine | None = None,
    mode: str = "cpu",
    translator: GoogleTranslator | None = None,
) -> ThreadingHTTPServer:
    """Bind to loopback only; expose fixed assets and a bounded CV-reading endpoint."""
    if mode not in MODES:
        raise ValueError(f"Unknown mode {mode!r}. Choose cpu, gpu, or basic.")
    parse_lock = threading.Lock()
    translator = translator if translator is not None else GoogleTranslator()
    search_service = job_service or JobSearchService(translator=translator)
    rules_only = mode == "basic"
    use_llm = engine is not None and not rules_only
    parse_timeout = PARSE_TIMEOUT_BASIC if rules_only else PARSE_TIMEOUT_MODEL
    reading = "basic" if rules_only else ("local-model" if use_llm else "unavailable")
    device = None if reading != "local-model" else mode

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            # Do not log uploaded content, file names, or extracted CV details.
            pass

        def _allowed(self) -> bool:
            actual_port = self.server.server_port
            hosts = {f"127.0.0.1:{actual_port}", f"localhost:{actual_port}"}
            origin = self.headers.get("Origin")
            if self.headers.get("Host") not in hosts:
                self._json(403, {"error": "This app is available on localhost only."})
                return False
            if origin is not None and origin not in {f"http://{host}" for host in hosts}:
                self._json(403, {"error": "Open the app on localhost to read a CV."})
                return False
            return True

        def _send(self, status: int, body: bytes, mime: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, payload: dict) -> None:
            self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self) -> None:
            if not self._allowed():
                return
            route = urlsplit(self.path).path
            if route == "/api/health":
                self._json(200, {"mode": reading, "device": device, "sample_jobs": False, "live_jobs": True, "cover_letter": use_llm, "interview_prep": True, "interview_stories": use_llm, "translate": search_service.settings.jobs_translate, "translate_to": search_service.settings.jobs_translate_to, "languages": language_choices()})
                return
            if route == "/api/providers":
                self._json(200, {"providers": search_service.registry.list()})
                return
            files = {"/desk-logic.js": ("desk-logic.js", "text/javascript"), "/desk.js": ("desk.js", "text/javascript"), "/coaching.js": ("coaching.js", "text/javascript"), "/jobs-store.js": ("jobs-store.js", "text/javascript"), "/": ("index.html", "text/html"), "/index.html": ("index.html", "text/html"), "/styles.css": ("styles.css", "text/css"), "/app.js": ("app.js", "text/javascript"), "/live-search.js": ("live-search.js", "text/javascript"), "/theme.js": ("theme.js", "text/javascript")}
            if route not in files:
                self._json(404, {"error": "Page not found."})
                return
            name, mime = files[route]
            try:
                body = (ASSETS / name).read_bytes()
            except OSError:
                self._json(404, {"error": "App files are missing. Run from the source checkout."})
                return
            self._send(200, body, f"{mime}; charset=utf-8")

        def _search_jobs(self) -> None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if self.headers.get("Transfer-Encoding") or not 0 < length <= 16384:
                    self._json(400, {"error": "Send a search request smaller than 16 KB."})
                    return
                self.connection.settimeout(180)
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("Expected a search options object.")
                providers = payload.pop("providers", None)
                translate_to = payload.pop("translate_to", None)
                if providers is not None and (not isinstance(providers, list) or not all(isinstance(p, str) for p in providers)):
                    raise ValueError("providers must be a list of source names.")
                if translate_to is not None and not isinstance(translate_to, str):
                    raise ValueError("Choose a supported description language.")
                query = JobSearchQuery.model_validate(payload)
                result = search_service.search(query, providers, translate_to=translate_to)
                self._json(502 if result.jobs_meta.status == "error" else 200, result.model_dump(mode="json"))
            except ValidationError as exc:
                messages = {
                    "workplace_type": "For work arrangement, choose On-site, Remote, or Hybrid. You can select more than one.",
                    "remoteFilter": "For work arrangement, choose On-site, Remote, or Hybrid. You can select more than one.",
                    "job_type": "Check your job types and choose from the available options.",
                    "jobType": "Check your job types and choose from the available options.",
                    "experience_level": "Check your experience levels and choose from the available options.",
                    "experienceLevel": "Check your experience levels and choose from the available options.",
                    "posted_within_days": "Enter a whole number of days between 1 and 365.",
                    "postedWithinDays": "Enter a whole number of days between 1 and 365.",
                    "keywords": "Enter a role or some keywords, using no more than 300 characters.",
                    "keyword": "Enter a role or some keywords, using no more than 300 characters.",
                    "limit": "Choose between 1 and 100 results.",
                    "page": "Choose a starting page between 0 and 1000.",
                }
                errors = exc.errors(include_url=False, include_input=False)
                fields = [item["loc"][0] for item in errors if item["loc"]]
                message = next((messages[field] for field in fields if field in messages), "Check your search options and choose from the available values.")
                self._json(400, {"error": message})
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
            except OSError:
                self._json(408, {"error": "The search request was incomplete. Please try again."})

        def _translate_text(self) -> None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if self.headers.get("Transfer-Encoding") or not 0 < length <= 40000:
                    self._json(400, {"error": "Send a description smaller than 20 KB to translate."})
                    return
                self.connection.settimeout(30)
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("Expected a translation request.")
                text = payload.get("text")
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("Add the job description to translate.")
                target = normalize_language(payload.get("target") or "en")
                if not target:
                    raise ValueError("Choose a supported description language.")
                source = payload.get("source")
                if source is not None and not isinstance(source, str):
                    raise ValueError("Choose a supported description language.")
                result = translator.translate(text, target, source if isinstance(source, str) else "auto")
                self._json(200, {"text": result.text, "source_language": result.source_language, "target": result.target_language, "translated": result.translated, "label": language_label(result.source_language)})
            except TranslationError as exc:
                self._json(502, {"error": str(exc)})
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
            except json.JSONDecodeError:
                self._json(400, {"error": "The translation request was not valid JSON."})
            except OSError:
                self._json(408, {"error": "The translation request was incomplete. Please try again."})

        def _cover_letter(self) -> None:
            if not use_llm or engine is None:
                self._json(503, {"error": "Cover letters need the local model. Start with --mode cpu or --mode gpu."})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if self.headers.get("Transfer-Encoding") or not 0 < length <= 96000:
                    self._json(400, {"error": "Send a cover-letter request smaller than 96 KB."})
                    return
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("Expected a cover-letter request.")
                profile, job, refresh = _cover_letter_payload(payload)
                options = cover_options(payload.get("options"))
                if not parse_lock.acquire(blocking=False):
                    self._json(429, {"error": "The local model is already busy. Try again when it finishes."})
                    return
                try:
                    self.connection.settimeout(PARSE_TIMEOUT_MODEL)
                    letter = generate_cover_letter(engine, profile, job, refresh, options=options)
                    self._json(200, {"letter": letter, "review": review_cover_letter(letter, profile, job, options), "options": options})
                finally:
                    parse_lock.release()
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
            except CoverLetterError as exc:
                self._json(502, {"error": str(exc)})
            except json.JSONDecodeError:
                self._json(400, {"error": "The cover-letter request was not valid JSON."})
            except OSError:
                self._json(408, {"error": "The cover-letter request was incomplete. Please try again."})
            except Exception:
                LOG.warning("A cover letter could not be generated; no profile or listing details were logged.")
                self._json(502, {"error": "The local model could not write this letter. Please try again."})

        def _interview_prep(self) -> None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if self.headers.get("Transfer-Encoding") or not 0 < length <= 96000:
                    self._json(400, {"error": "Send an interview-prep request smaller than 96 KB."})
                    return
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("Expected an interview-prep request.")
                profile, job, refresh = _cover_letter_payload(payload)
                if use_llm and engine is not None:
                    if not parse_lock.acquire(blocking=False):
                        self._json(429, {"error": "The local model is already busy. Try again when it finishes."})
                        return
                    try:
                        self.connection.settimeout(PARSE_TIMEOUT_MODEL)
                        pack = generate_interview_prep(engine, profile, job, refresh)
                    finally:
                        parse_lock.release()
                else:
                    pack = generate_interview_prep(None, profile, job, refresh)
                self._json(200, pack)
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
            except json.JSONDecodeError:
                self._json(400, {"error": "The interview-prep request was not valid JSON."})
            except OSError:
                self._json(408, {"error": "The interview-prep request was incomplete. Please try again."})
            except Exception:
                LOG.warning("Interview prep could not be built; no profile or listing details were logged.")
                self._json(502, {"error": "Interview prep could not be built. Please try again."})

        def _coaching(self, route: str) -> None:
            """Read-only analysis and single-session generation share strict input limits."""
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if self.headers.get("Transfer-Encoding") or not 0 < length <= 96000:
                    raise ValueError("Send a practice request smaller than 96 KB.")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("Send a profile and listing as JSON.")
                profile, job, _ = _cover_letter_payload(payload)
                if route == "/api/role-analysis":
                    self._json(200, build_role_context(profile, job))
                    return
                if route == "/api/cover-letter-review":
                    letter = _clip(payload.get("letter"), 8000)
                    if not letter:
                        raise ValueError("Write a draft before checking it.")
                    self._json(200, review_cover_letter(letter, profile, job, cover_options(payload.get("options"))))
                    return
                if route == "/api/cover-letter-revise":
                    if not use_llm or engine is None:
                        self._json(503, {"error": "Rewriting needs the local model. Your original text is kept."})
                        return
                    if not parse_lock.acquire(blocking=False):
                        self._json(429, {"error": "The local model is busy. Try the revision again shortly."})
                        return
                    try:
                        self.connection.settimeout(PARSE_TIMEOUT_MODEL)
                        letter = payload.get("letter")
                        if not isinstance(letter, str):
                            raise ValueError("Include the letter to revise.")
                        self._json(200, revise_cover_passage(engine, profile, job, letter,
                            payload.get("start"), payload.get("end"), payload.get("instruction"),
                            cover_options(payload.get("options"))))
                    finally:
                        parse_lock.release()
                    return
                skill_id = _clip(payload.get("skill_id"), 32)
                mode = _clip(payload.get("mode"), 20) or None
                feedback = route == "/api/practice-feedback"
                tailor = payload.get("tailor") is True or feedback
                active_engine = engine if tailor and use_llm else None
                if active_engine is not None and not parse_lock.acquire(blocking=False):
                    self._json(429, {"error": "The local model is busy. Your saved practice is still available."})
                    return
                try:
                    self.connection.settimeout(PARSE_TIMEOUT_MODEL if active_engine else PARSE_TIMEOUT_BASIC)
                    lesson = generate_practice_lesson(None if feedback else active_engine, profile, job, skill_id, mode,
                        focus=_clip(payload.get("focus"), 1200))
                    if feedback:
                        # The learner may be answering a generated variation, not the default exercise.
                        supplied = payload.get("lesson")
                        if not isinstance(supplied, dict):
                            raise ValueError("Include the exercise you are answering.")
                        exercise = _clip(supplied.get("exercise"), 2000)
                        criteria = _string_list(supplied.get("criteria"), 4, 400)
                        if len(exercise) < 20 or len(criteria) < 2:
                            raise ValueError("Include the complete exercise and self-checks.")
                        lesson.update(exercise=exercise, criteria=criteria)
                        self._json(200, review_practice_answer(active_engine, lesson, _clip(payload.get("answer"), 5000)))
                    else:
                        self._json(200, {"lesson": lesson})
                finally:
                    if active_engine is not None:
                        parse_lock.release()
            except json.JSONDecodeError:
                self._json(400, {"error": "The practice request was not valid JSON."})
            except CoverLetterError as exc:
                self._json(422, {"error": str(exc)})
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
            except OSError:
                self._json(408, {"error": "The request was incomplete. Try again."})
            except Exception:
                LOG.warning("Coaching request failed; no profile, answer or listing details were logged.")
                self._json(502, {"error": "Practice could not be prepared. Your saved work is unchanged."})

        def do_POST(self) -> None:
            if not self._allowed():
                return
            if urlsplit(self.path).path in {"/api/role-analysis", "/api/cover-letter-review", "/api/cover-letter-revise", "/api/practice-lesson", "/api/practice-feedback"}:
                self._coaching(urlsplit(self.path).path)
                return
            if urlsplit(self.path).path == "/api/jobs":
                self._search_jobs()
                return
            if urlsplit(self.path).path == "/api/translate":
                self._translate_text()
                return
            if urlsplit(self.path).path == "/api/cover-letter":
                self._cover_letter()
                return
            if urlsplit(self.path).path == "/api/interview-prep":
                self._interview_prep()
                return
            if urlsplit(self.path).path != "/api/parse":
                self._json(404, {"error": "Page not found."})
                return
            extension = self.headers.get("X-CV-Extension", "").lower()
            if extension not in {"pdf", "docx", "txt"}:
                self._json(400, {"error": "Choose a PDF, Word (.docx), or text CV."})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if self.headers.get("Transfer-Encoding") or length <= 0:
                self._json(400, {"error": "Choose a non-empty CV file."})
                return
            if length > MAX_UPLOAD:
                self._json(413, {"error": "Please choose a file smaller than 5 MB."})
                return
            if not rules_only and engine is None:
                self._json(503, {"error": NO_MODEL_HELP})
                return
            if not parse_lock.acquire(blocking=False):
                self._json(429, {"error": "A CV is already being read. Please try again when it finishes."})
                return
            try:
                self.connection.settimeout(parse_timeout)
                body = self.rfile.read(length)
                if len(body) != length:
                    self._json(400, {"error": "The file upload was incomplete. Please try again."})
                    return
                with tempfile.TemporaryDirectory(prefix="ats-app-") as folder:
                    cv_path = Path(folder) / f"cv.{extension}"
                    cv_path.write_bytes(body)
                    profile, document = parse_cv(
                        cv_path,
                        rules_only=rules_only,
                        model_path=model,
                        engine=engine,
                    )
                    data = profile.public_dump()
                    public_profile = {key: data.get(key) for key in PARSE_PROFILE_FIELDS}
                    self._json(200, {"profile": public_profile, "text": document.text[:50000], "quality": document.quality, "mode": reading})
            except Exception:
                # Exception messages can contain paths or CV excerpts. Keep them private.
                LOG.warning("A CV could not be read; no document details were logged.")
                self._json(422, {"error": "This document could not be read. Try a text-based PDF, a Word file, or a text CV. Check that the language model is installed and available."})
            finally:
                parse_lock.release()

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def launch(*, port: int = 8765, model: Path | None = None, mode: str = "cpu") -> None:
    """Start the loopback server. Raises ValueError or ExtractionError on bad setup."""
    if mode not in MODES:
        raise ValueError(f"Unknown mode {mode!r}. Choose cpu, gpu, or basic.")
    if not 1 <= port <= 65535:
        raise ValueError("Choose a port between 1 and 65535.")
    resolved = None if mode == "basic" else resolve_model(model)
    engine = None
    if mode != "basic":
        if resolved is None or not resolved.is_file():
            raise ValueError(NO_MODEL_HELP)
        engine = create_engine(resolved, n_gpu_layers=gpu_layers_for_mode(mode))
        if engine is None:
            raise ValueError(NO_MODEL_HELP)
    try:
        server = create_server(port, resolved, engine=engine, mode=mode)
    except OSError as exc:
        raise ValueError(f"Could not start the local app: {exc}") from exc
    print(f"ATS Matcher: http://127.0.0.1:{server.server_port}", flush=True)
    if mode == "basic":
        print("CV reading: basic (no model). Use --mode cpu or --mode gpu for AI matching.", flush=True)
    else:
        device = "GPU" if mode == "gpu" else "CPU"
        print(f"CV reading: AI matching on {device} ({resolved.name}). Same matcher as ats-match parse.", flush=True)
    print("Live job search and local application tracking. Loopback only. Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the ATS Matcher local app (localhost only).")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--model", type=Path, help="Local GGUF model. Defaults to LLAMA_MODEL_PATH, then a .gguf file in .models.")
    parser.add_argument(
        "--mode",
        choices=MODES,
        default="cpu",
        help="cpu: AI matching on CPU (default). gpu: AI matching on GPU. basic: regex/contact fields only, no model.",
    )
    args = parser.parse_args()
    try:
        launch(port=args.port, model=args.model, mode=args.mode)
    except (ValueError, ExtractionError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
