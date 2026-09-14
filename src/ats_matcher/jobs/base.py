from __future__ import annotations
from typing import Protocol, runtime_checkable
from ats_matcher.schemas.jobs import JobSearchQuery, ProviderResult


class ProviderError(Exception):
    """A safe, actionable upstream failure; never contains the user's profile."""
    def __init__(self, code: str, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


@runtime_checkable
class JobProvider(Protocol):
    name: str
    def search(self, query: JobSearchQuery, limit: int | None = None) -> ProviderResult: ...
