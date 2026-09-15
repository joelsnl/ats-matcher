"""Optional Indeed integration through python-jobspy.

JobSpy owns HTTP timeouts/retries. No proxy configuration is supplied here.
"""
from __future__ import annotations

import json
import subprocess
import sys
from importlib.util import find_spec

from ats_matcher.jobs.base import ProviderError
from ats_matcher.jobs.cache import JobCache
from ats_matcher.jobs.providers.ats import _matches, _text, date_days, make_job, normalize_type, posted_date, unsupported_filters, with_skills
from ats_matcher.schemas.jobs import ProviderResult


class IndeedProvider:
    name = "indeed"

    def __init__(self, country="usa", cache_ttl=900, fetch_descriptions=True, *, scrape=None):
        self.country, self.fetch_descriptions = country, fetch_descriptions
        self.cache = JobCache(ttl=cache_ttl)
        self._scrape = scrape

    def _get_scraper(self):
        if self._scrape is None:
            if find_spec("jobspy") is None:
                raise ProviderError("dependency_missing", 'Indeed requires the optional extra: pip install -e ".[indeed]"')
            self._scrape = _isolated_scrape
        return self._scrape

    def _job(self, row):
        salary = None
        minimum, maximum = _text(row.get("min_amount")), _text(row.get("max_amount"))
        if minimum or maximum:
            salary = " ".join(part for part in (_text(row.get("currency")), "–".join(v for v in (minimum, maximum) if v), _text(row.get("interval"))) if part)
        return make_job(
            title=row.get("title"), company=row.get("company"), location=row.get("location"),
            url=row.get("job_url"), job_id=_text(row.get("id")) or _text(row.get("job_url")), source=self.name,
            description=row.get("description") if self.fetch_descriptions else None,
            posted_at=str(row["date_posted"]) if row.get("date_posted") is not None else None,
            employment_type=normalize_type(_text(row.get("job_type"))),
            workplace_type="remote" if row.get("is_remote") is True else None, salary=salary,
        )

    def search(self, query, limit=None):
        unsupported_filters(query)
        if query.career_url:
            raise ProviderError("unsupported_filter", "Career URLs are supported by Greenhouse, Lever, and Ashby.")
        workplaces = query.workplace_type if isinstance(query.workplace_type, list) else [query.workplace_type]
        if any(item in {"on_site", "hybrid"} for item in workplaces):
            raise ProviderError("unsupported_filter", "Indeed can identify remote work but cannot distinguish hybrid from on-site.")
        limit = query.limit if limit is None else limit
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        # Use country from query if provided, otherwise use default
        country = query.indeed_country.strip().lower() if query.indeed_country else self.country
        key = f"{country}:{query.model_dump_json()}:{limit}"
        cached = self.cache.get(key)
        if cached is not None:
            cached.cached = True
            return cached
        scrape = self._get_scraper()
        try:
            # JobSpy cannot combine hours_old with its job_type/is_remote filters.
            # Request dates upstream and apply the other available fields locally.
            frame = scrape(site_name=["indeed"], search_term=query.keywords, location=query.location,
                country_indeed=country, results_wanted=limit, offset=query.page * limit,
                hours_old=date_days(query) * 24 if date_days(query) else None, description_format="plain", verbose=0)
            rows = frame if isinstance(frame, list) else ([] if frame is None else frame.to_dict("records"))
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError("fetch_error", "Indeed search failed. Check JOBS_INDEED_COUNTRY and try again later.") from exc
        jobs, seen, skipped = [], set(), 0
        for row in rows:
            try:
                job = self._job(row)
            except (ValueError, TypeError, AttributeError):
                job = None
            if job is None:
                skipped += 1
            elif job.job_id not in seen and _matches(job, query, keywords=False, location=False):
                jobs.append(job)
                seen.add(job.job_id)
        warnings = []
        if query.job_type or query.workplace_type:
            warnings.append("Work arrangement and job type are matched against this source page; Next source page continues the search.")
        if skipped:
            warnings.append(f"Skipped {skipped} invalid listings.")
        if query.sort_by == "recent":
            jobs.sort(key=lambda job: posted_date(job.posted_at).timestamp() if posted_date(job.posted_at) else 0, reverse=True)
            warnings.append("Indeed results are sorted by date within this source page only.")
        result = ProviderResult(provider=self.name, jobs=with_skills(jobs[:limit]), returned=len(jobs[:limit]), pages_fetched=1,
            next_page=query.page + 1 if len(rows) >= limit else None,
            status="partial" if warnings else "ok", warnings=warnings)
        self.cache.set(key, result)
        return result


def _isolated_scrape(**kwargs):
    """Keep JobSpy's native TLS library outside the HTTP server process."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "ats_matcher.jobs.providers.indeed_worker"],
            input=json.dumps(kwargs), capture_output=True, text=True, encoding="utf-8",
            timeout=120,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except subprocess.TimeoutExpired as exc:
        raise ProviderError("fetch_error", "Indeed search timed out. Try again later or choose another source.") from exc
    if result.returncode:
        raise ProviderError("fetch_error", "Indeed's search worker stopped unexpectedly. Try another source or reinstall the optional Indeed package.")
    return json.loads(result.stdout)
