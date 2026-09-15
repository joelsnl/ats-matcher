"""Bounded JSON transport for public job APIs."""
from __future__ import annotations

import json
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

from ats_matcher.jobs.base import ProviderError
from ats_matcher.jobs.providers.linkedin import NoRedirect, retry_after_seconds

MAX_RESPONSE_BYTES = 20 * 1024 * 1024


def fetch_json(url: str, timeout: float):
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "ATSMatcher/0.2 (public job search)"})
    with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ProviderError("invalid_response", "The job source response exceeded the size limit.")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise ProviderError("invalid_response", "The job source did not return valid JSON.") from exc


class PublicAPI:
    def __init__(self, *, timeout=15, retries=2, delay=2, fetch=None, sleep=time.sleep, clock=time.monotonic):
        self.timeout, self.retries, self.delay = timeout, retries, delay
        self.fetch, self.sleep, self.clock = fetch or fetch_json, sleep, clock
        self._last_request = None
        self._lock = threading.Lock()

    def request(self, url):
        for attempt in range(self.retries + 1):
            try:
                with self._lock:
                    if self._last_request is not None:
                        self.sleep(max(0, self.delay - (self.clock() - self._last_request)))
                    self._last_request = self.clock()
                    return self.fetch(url, self.timeout)
            except HTTPError as exc:
                code = exc.code
                retry_after = retry_after_seconds(exc.headers.get("Retry-After", "")) if exc.headers else None
                exc.close()
                error_code = {404: "board_not_found", 401: "access_denied", 403: "access_denied", 429: "rate_limited"}.get(code, "temporarily_unavailable" if code >= 500 else "http_error")
                failure = ProviderError(error_code, f"The job source returned HTTP {code}.", retry_after=retry_after)
                retryable = code == 429 or code >= 500
            except (URLError, TimeoutError, OSError):
                failure = ProviderError("connection_error", "Could not reach the job source.")
                retry_after, retryable = None, True
            if not retryable or attempt == self.retries or (retry_after is not None and retry_after > 60):
                raise failure
            self.sleep(max(2 ** attempt, retry_after or 0))


def records(payload, key=None):
    value = payload.get(key) if key and isinstance(payload, dict) else payload if key is None else None
    if not isinstance(value, list):
        raise ProviderError("invalid_response", "The job source returned an unexpected record list.")
    return value
