from __future__ import annotations

from typing import Protocol, runtime_checkable

from ats_matcher.schemas.jobs import Job, JobSearchQuery


@runtime_checkable
class JobProvider(Protocol):
    name: str

    def search(self, query: JobSearchQuery, limit: int = 15) -> list[Job]:
        """Return live jobs. Must not invent URLs."""


class NotImplementedProvider:
    """Placeholder until Phase 5."""

    name = "not_implemented"

    def search(self, query: JobSearchQuery, limit: int = 15) -> list[Job]:
        raise NotImplementedError(
            "Job search is Phase 5. Use `ats-match parse` for CV extraction."
        )
