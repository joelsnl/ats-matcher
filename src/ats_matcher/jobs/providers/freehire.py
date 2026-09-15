"""Freehire's public search API; see https://freehire.me/docs/api."""
from __future__ import annotations

from urllib.parse import urlencode

from ats_matcher.jobs.base import ProviderError
from ats_matcher.jobs.cache import JobCache
from ats_matcher.jobs.providers.ats import _matches, date_days, make_job, normalize_type, unsupported_filters, with_skills
from ats_matcher.jobs.providers.public_api import PublicAPI, records
from ats_matcher.schemas.jobs import ProviderResult


class FreehireProvider:
    name = "freehire"

    def __init__(self, timeout=15, retries=2, delay=2, cache_ttl=900, fetch_descriptions=True, *, fetch=None, sleep=None):
        self.api = PublicAPI(timeout=timeout, retries=retries, delay=delay, fetch=fetch, **({"sleep": sleep} if sleep else {}))
        self.cache = JobCache(ttl=cache_ttl)
        self.fetch_descriptions = fetch_descriptions

    def _url(self, query, limit):
        params = {"q": query.keywords, "limit": limit, "offset": query.page * limit}
        if date_days(query):
            params["posted_within_days"] = date_days(query)
        if query.sort_by == "recent":
            params.update(sort="posted_at", order="desc")
        for name, value in (("work_mode", query.workplace_type), ("employment_type", query.job_type)):
            if value:
                values = value if isinstance(value, list) else [value]
                params[name] = ",".join("onsite" if item == "on_site" else item for item in values)
        path = "agent/jobs/search" if self.fetch_descriptions else "jobs/search"
        if self.fetch_descriptions:
            params["description_format"] = "text"
        return f"https://freehire.me/api/v1/{path}?" + urlencode(params)

    def _job(self, row):
        if row.get("closed_at"):
            return None
        enrichment = row.get("enrichment") or {}
        return make_job(
            title=row.get("title"), company=row.get("company"), location=row.get("location"),
            url=row.get("url"), job_id=row.get("public_slug"), source=self.name,
            description=row.get("description") if self.fetch_descriptions else None,
            posted_at=row.get("posted_at"), workplace_type=normalize_type(row.get("work_mode"), workplace=True),
            employment_type=normalize_type(row.get("employment_type") or enrichment.get("employment_type")),
        )

    def search(self, query, limit=None):
        unsupported_filters(query)
        if query.career_url:
            raise ProviderError("unsupported_filter", "Career URLs are supported by Greenhouse, Lever, and Ashby.")
        limit = query.limit if limit is None else limit
        if not 1 <= limit <= 100 or (query.page + 1) * limit > 10000:
            raise ProviderError("invalid_page", "Freehire requires a limit of 1–100 and offset + limit no greater than 10000.")
        types = query.job_type if isinstance(query.job_type, list) else [query.job_type]
        if any(kind in {"temporary", "volunteer"} for kind in types):
            raise ProviderError("unsupported_filter", "Freehire does not support temporary or volunteer filters.")
        key = f"{query.model_dump_json()}:{limit}"
        cached = self.cache.get(key)
        if cached is not None:
            cached.cached = True
            return cached
        payload = self.api.request(self._url(query, limit))
        rows = records(payload, "data")
        meta = payload.get("meta")
        if not isinstance(meta, dict) or not isinstance(meta.get("total"), int) or meta["total"] < 0:
            raise ProviderError("invalid_response", "Freehire returned invalid pagination metadata.")
        if meta.get("ignored_params"):
            raise ProviderError("unsupported_filter", "Freehire ignored a requested filter; search results were discarded.")
        jobs, seen, skipped = [], set(), 0
        for row in rows:
            try:
                job = self._job(row) if isinstance(row, dict) else None
            except (ValueError, TypeError, AttributeError):
                job = None
            if job is None:
                skipped += 1
            elif job.job_id not in seen and _matches(job, query, keywords=False):
                jobs.append(job)
                seen.add(job.job_id)
        warnings = []
        if query.location:
            warnings.append("Location is matched against this source page only; use Next source page to continue.")
        if skipped:
            warnings.append(f"Skipped {skipped} closed or invalid listings.")
        result = ProviderResult(provider=self.name, jobs=with_skills(jobs[:limit]), returned=len(jobs[:limit]), pages_fetched=1,
            next_page=query.page + 1 if rows and (query.page + 1) * limit < min(meta["total"], 10000) else None,
            status="partial" if warnings else "ok", warnings=warnings)
        self.cache.set(key, result)
        return result
