"""Ashby public job posting API."""
from __future__ import annotations

from ats_matcher.jobs.providers.ats import ATSProvider, make_job, normalize_type


class AshbyProvider(ATSProvider):
    name = "ashby"
    endpoint = "https://api.ashbyhq.com/posting-api/job-board/{board}"

    def _records(self, payload):
        return [row for row in super()._records(payload) if not isinstance(row, dict) or row.get("isListed") is not False]

    def _job(self, record, board):
        if record.get("isListed") is False:
            return None
        locations = [record.get("location")]
        for secondary in record.get("secondaryLocations") or []:
            if isinstance(secondary, dict):
                locations.append(secondary.get("location"))
        workplace = normalize_type(record.get("workplaceType"), workplace=True)
        if not workplace and record.get("isRemote") is True:
            workplace = "remote"
        return make_job(
            title=record.get("title"), company=self.company_name(board),
            location="; ".join(loc for loc in locations if isinstance(loc, str)),
            url=record.get("jobUrl") or record.get("applyUrl"),
            job_id=f"ashby:{board}:{record.get('jobUrl') or record.get('applyUrl')}",
            source=self.name,
            description=(record.get("descriptionPlain") or record.get("descriptionHtml")) if self.fetch_descriptions else None,
            posted_at=record.get("publishedAt"), workplace_type=workplace,
            employment_type=normalize_type(record.get("employmentType")),
        )
