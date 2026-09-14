"""Translate job descriptions with Google Translate's public widget endpoints.

translate-pa is tried first; the older gtx endpoint is the fallback. These are
public widget keys, not a Cloud Translation credential. Descriptions are sent
to Google only when they do not already look like the chosen language.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html import unescape
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ats_matcher.schemas.jobs import Job

ENDPOINT_PA = "https://translate-pa.googleapis.com/v1/translate"
ENDPOINT_GTX = "https://translate.googleapis.com/translate_a/single"
# Public widget key used by Google's Translate Element.
PA_KEY = "AIzaSyDLEeFI5OtFBwYBIoK_jj5m32rZK5CkCXA"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
CHUNK = 1500
LANGUAGES = {
    "en": "English",
    "nl": "Dutch",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "pl": "Polish",
    "sv": "Swedish",
    "da": "Danish",
    "no": "Norwegian",
    "fi": "Finnish",
    "cs": "Czech",
    "hu": "Hungarian",
    "ro": "Romanian",
    "el": "Greek",
    "tr": "Turkish",
    "ru": "Russian",
    "uk": "Ukrainian",
    "ar": "Arabic",
    "he": "Hebrew",
    "hi": "Hindi",
    "ja": "Japanese",
    "ko": "Korean",
    "zh-CN": "Chinese (Simplified)",
    "zh-TW": "Chinese (Traditional)",
    "id": "Indonesian",
    "vi": "Vietnamese",
    "th": "Thai",
}
LANGUAGE_ALIASES = {"zh": "zh-CN", "zh-cn": "zh-CN", "zh-tw": "zh-TW", "nb": "no", "nn": "no", "iw": "he"}
ENGLISH_MARKERS = {"the", "and", "to", "of", "a", "in", "for", "with", "you", "your", "we", "this", "that", "are", "is", "or", "be", "as", "on", "at", "will", "from", "our"}
FOREIGN_MARKERS = {
    "een", "het", "van", "voor", "wij", "niet", "als", "aan", "bij", "ook", "naar",
    "und", "der", "die", "das", "für", "nicht", "eine", "mit", "sich", "auf",
    "les", "des", "une", "pour", "vous", "dans", "est", "que", "nous",
    "los", "las", "una", "para", "por", "como", "con",
    "gli", "che", "non", "per",
    "não", "uma", "os",
}
SCRIPT_RE = re.compile(r"[\u0400-\u04ff\u0600-\u06ff\u0900-\u097f\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af\u0590-\u05ff]")
TOKEN_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
LANGUAGE_RE = re.compile(r"^[a-z]{2}(?:-[A-Za-z]{2,4})?$")


class TranslationError(Exception):
    """Visible, non-secret translation failure."""


@dataclass(frozen=True)
class Translation:
    text: str
    source_language: str | None
    target_language: str
    translated: bool


def language_choices() -> list[dict[str, str]]:
    return [{"id": code, "label": label} for code, label in LANGUAGES.items()]


def language_label(code: str | None) -> str:
    if not code:
        return "the original language"
    return LANGUAGES.get(code, code)


def normalize_language(value: str | None) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw or raw.lower() in {"off", "none", "original", "false", "0"}:
        return None
    mapped = LANGUAGE_ALIASES.get(raw.lower(), raw)
    if mapped in LANGUAGES:
        return mapped
    if mapped[:2].lower() in LANGUAGES:
        return mapped[:2].lower()
    raise ValueError("Choose a supported description language.")


def looks_english(text: str) -> bool:
    if not text or not text.strip():
        return True
    if SCRIPT_RE.search(text):
        return False
    tokens = [token.lower() for token in TOKEN_RE.findall(text)]
    if len(tokens) < 12:
        return not any(token in FOREIGN_MARKERS for token in tokens)
    english = sum(token in ENGLISH_MARKERS for token in tokens)
    foreign = sum(token in FOREIGN_MARKERS for token in tokens)
    if foreign >= 4:
        return False
    return english / max(len(tokens), 1) >= 0.12 and english > foreign


def chunk_text(text: str, limit: int = CHUNK) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    for part in re.split(r"\n{2,}", text):
        extra = len(part) + (2 if buf else 0)
        if buf and size + extra > limit:
            chunks.append("\n\n".join(buf))
            buf, size = [part], len(part)
        else:
            buf.append(part)
            size += extra
    if buf:
        chunks.append("\n\n".join(buf))
    split: list[str] = []
    for chunk in chunks:
        if len(chunk) <= limit:
            split.append(chunk)
            continue
        for index in range(0, len(chunk), limit):
            split.append(chunk[index:index + limit])
    return split


def _language_code(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    code = LANGUAGE_ALIASES.get(value.strip(), value.strip())
    if code in LANGUAGES:
        return code
    if LANGUAGE_RE.fullmatch(code) and len(code) <= 12:
        lowered = code[:2].lower()
        return lowered if lowered in LANGUAGES else None
    return None


def _request(method: str, url: str, *, data: bytes | None = None, headers: dict[str, str] | None = None, timeout: float = 15.0) -> tuple[int, str, dict[str, str]]:
    request = Request(url, data=data, method=method, headers={"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})})
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read(2 * 1024 * 1024 + 1)
            if len(body) > 2 * 1024 * 1024:
                raise TranslationError("Google Translate returned an unexpectedly large response.")
            return response.status, body.decode("utf-8", errors="replace"), dict(response.headers.items())
    except HTTPError as exc:
        if exc.code == 429:
            raise TranslationError("Google Translate is limiting requests. Try again in a moment.") from exc
        raise TranslationError(f"Google Translate returned HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise TranslationError("Could not reach Google Translate. Check the connection and try again.") from exc


class GoogleTranslator:
    def __init__(self, *, timeout: float = 15.0, request=_request):
        self.timeout = timeout
        self._request = request
        self._cache: dict[tuple[str, str], Translation] = {}

    def _fetch(self, method: str, url: str, **kwargs) -> tuple[int, str, dict[str, str]]:
        try:
            return self._request(method, url, **kwargs)
        except TranslationError:
            raise
        except HTTPError as exc:
            if exc.code == 429:
                raise TranslationError("Google Translate is limiting requests. Try again in a moment.") from exc
            raise TranslationError(f"Google Translate returned HTTP {exc.code}.") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise TranslationError("Could not reach Google Translate. Check the connection and try again.") from exc

    def translate(self, text: str, target: str = "en", source: str | None = "auto") -> Translation:
        target = normalize_language(target) or "en"
        original = (text or "").strip()
        if not original:
            return Translation("", None, target, False)
        if len(original) > 20000:
            raise TranslationError("That description is too long to translate.")
        cached = self._cache.get((original, target))
        if cached:
            return cached
        source_code = None if source in {None, "", "auto"} else normalize_language(source)
        if looks_english(original) and target == "en":
            result = Translation(original, "en", target, False)
            self._cache[(original, target)] = result
            return result
        parts = []
        detected = source_code
        for chunk in chunk_text(original):
            translated, found = self._translate_chunk(chunk, target, source_code or "auto")
            parts.append(translated)
            detected = detected or found
        joined = "\n\n".join(parts).strip()
        if not joined or (detected or "").lower() == target.lower() or joined == original:
            result = Translation(original, detected or ("en" if target == "en" else None), target, False)
        else:
            result = Translation(joined[:20000], detected, target, True)
        self._cache[(original, target)] = result
        return result

    def _translate_chunk(self, text: str, target: str, source: str) -> tuple[str, str | None]:
        errors = []
        for engine in (self._translate_pa, self._translate_gtx):
            try:
                return engine(text, target, source)
            except TranslationError as exc:
                errors.append(str(exc))
                if "limiting" in str(exc).lower():
                    raise
        raise TranslationError(errors[-1] if errors else "Google Translate did not return a translation.")

    def _translate_pa(self, text: str, target: str, source: str) -> tuple[str, str | None]:
        params = {
            "params.client": "gtx",
            "query.source_language": source or "auto",
            "query.target_language": target,
            "query.display_language": "en-US",
            "data_types": "TRANSLATION",
            "key": PA_KEY,
            "query.text": text,
        }
        status, body, _ = self._fetch("GET", ENDPOINT_PA + "?" + urlencode(params), timeout=self.timeout)
        if status != 200:
            raise TranslationError(f"Google Translate returned HTTP {status}.")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise TranslationError("Google Translate returned an unreadable response.") from exc
        translated = unescape(str((payload or {}).get("translation") or "")).strip()
        if not translated:
            raise TranslationError("Google Translate returned an empty translation.")
        detected = _language_code(
            payload.get("sourceLanguage") or payload.get("detectedSourceLanguage") or payload.get("src")
        )
        return translated, detected

    def _translate_gtx(self, text: str, target: str, source: str) -> tuple[str, str | None]:
        params = {"client": "gtx", "sl": source or "auto", "tl": target, "dt": "t", "dj": "1", "q": text}
        encoded = urlencode(params).encode("utf-8")
        if len(text) <= 1800:
            status, body, _ = self._fetch("GET", ENDPOINT_GTX + "?" + urlencode(params), timeout=self.timeout)
        else:
            status, body, _ = self._fetch(
                "POST",
                ENDPOINT_GTX,
                data=encoded,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=self.timeout,
            )
        if status != 200:
            raise TranslationError(f"Google Translate returned HTTP {status}.")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise TranslationError("Google Translate returned an unreadable response.") from exc
        sentences = payload.get("sentences") if isinstance(payload, dict) else None
        translated = "".join(item.get("trans", "") for item in sentences or [] if isinstance(item, dict)).strip()
        if not translated:
            raise TranslationError("Google Translate returned an empty translation.")
        detected = _language_code(payload.get("src") if isinstance(payload, dict) else None)
        return unescape(translated), detected


def translate_jobs(jobs: list[Job], target: str, translator: GoogleTranslator, warnings: list[str] | None = None) -> list[Job]:
    notes = warnings if warnings is not None else []
    translated_count = 0
    failed = 0
    updated: list[Job] = []
    for job in jobs:
        if not job.description:
            updated.append(job)
            continue
        try:
            result = translator.translate(job.description, target)
        except TranslationError as exc:
            failed += 1
            notes.append(str(exc))
            updated.append(job)
            if "limiting" in str(exc).lower():
                updated.extend(jobs[len(updated):])
                break
            continue
        if not result.translated:
            updated.append(job.model_copy(update={"source_language": result.source_language or job.source_language}))
            continue
        translated_count += 1
        updated.append(job.model_copy(update={
            "source_language": result.source_language,
            "translated_description": result.text,
            "translation_language": result.target_language,
        }))
    if translated_count:
        notes.append(f"Translated {translated_count} listing{'s' if translated_count != 1 else ''} into {language_label(target)}. The original text is kept.")
    if failed:
        notes.append(f"Could not translate {failed} listing{'s' if failed != 1 else ''}; showing the original text.")
    # Deduplicate identical warning strings while keeping order.
    seen = set()
    notes[:] = [note for note in notes if not (note in seen or seen.add(note))]
    return updated
