"""Greenhouse's public Job Board API."""
from __future__ import annotations

from ats_matcher.jobs.providers.ats import ATSProvider, make_job


class GreenhouseProvider(ATSProvider):
    name = "greenhouse"
    unsupported_options = ("job_type", "workplace_type")
    endpoint = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs"

    def _url(self, board):
        return super()._url(board) + ("?content=true" if self.fetch_descriptions else "")

    def _job(self, record, board):
        # updated_at is an edit timestamp, not a publication date.
        return make_job(
            title=record.get("title"), company=record.get("company_name") or self.company_name(board),
            location=(record.get("location") or {}).get("name"), url=record.get("absolute_url"),
            job_id=f"greenhouse:{board}:{record.get('id') or record.get('absolute_url')}",
            source=self.name, description=record.get("content") if self.fetch_descriptions else None,
            posted_at=record.get("first_published"),
        )
