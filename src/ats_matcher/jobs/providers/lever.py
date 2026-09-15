"""Lever public postings, including EU-hosted boards."""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote

from ats_matcher.jobs.providers.ats import ATSProvider, make_job, normalize_type
from ats_matcher.jobs.providers.public_api import records


class LeverProvider(ATSProvider):
    name = "lever"

    def _url(self, board):
        region = "eu." if board.startswith("eu:") else ""
        return f"https://api.{region}lever.co/v0/postings/{quote(board.removeprefix('eu:'), safe='')}?mode=json"

    def _records(self, payload):
        return records(payload)

    def _job(self, record, board):
        categories = record.get("categories") or {}
        locations = categories.get("allLocations") or [categories.get("location")]
        location = "; ".join(loc for loc in locations if isinstance(loc, str))
        description = None
        if self.fetch_descriptions:
            parts = [record.get("descriptionPlain") or record.get("description") or ""]
            for section in record.get("lists") or []:
                if isinstance(section, dict):
                    parts.extend([section.get("text") or "", section.get("content") or ""])
            parts.append(record.get("additionalPlain") or record.get("additional") or "")
            description = "\n".join(parts)
        created = record.get("createdAt")
        posted = None
        if isinstance(created, (int, float)):
            try:
                posted = datetime.fromtimestamp(created / 1000, timezone.utc).isoformat()
            except (ValueError, OverflowError, OSError):
                pass
        return make_job(
            title=record.get("text"), company=self.company_name(board), location=location,
            url=record.get("hostedUrl") or record.get("applyUrl"),
            job_id=f"lever:{board}:{record.get('id') or record.get('hostedUrl') or record.get('applyUrl')}",
            source=self.name, description=description, posted_at=posted,
            employment_type=normalize_type(categories.get("commitment")),
            workplace_type=normalize_type(record.get("workplaceType"), workplace=True),
        )
