"""Shared normalization and search for finite public company boards."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote

from ats_matcher.jobs.ats_detector import ATSDetector, BOARD_SLUG
from ats_matcher.jobs.base import ProviderError
from ats_matcher.jobs.cache import JobCache
from ats_matcher.jobs.company_registry import CompanyRegistry
from ats_matcher.jobs.providers.public_api import PublicAPI, records
from ats_matcher.jobs.skills import mentioned_skills
from ats_matcher.schemas.jobs import Job, JobSearchQuery, ProviderResult


def _text(value: Any) -> str | None:
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return None
    text = str(value).strip()
    return text if text and text.lower() not in {"nan", "nat", "none", "<na>"} else None


class _DescriptionParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag in {"p", "div", "li", "br", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in {"p", "div", "li"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain_text(value):
    text = _text(value)
    if not text:
        return None
    parser = _DescriptionParser()
    parser.feed(unescape(unescape(text)))
    return "\n".join(line for part in "".join(parser.parts).splitlines() if (line := " ".join(part.split())))[:20000] or None


def normalize_type(value, *, workplace=False):
    key = re.sub(r"[\s_-]", "", (_text(value) or "").lower())
    mapping = {"remote": "remote", "hybrid": "hybrid", "onsite": "on_site"} if workplace else {
        "fulltime": "full_time", "parttime": "part_time", "contract": "contract", "intern": "internship",
        "internship": "internship", "temporary": "temporary", "volunteer": "volunteer",
    }
    return mapping.get(key)


def posted_date(value):
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return date.replace(tzinfo=timezone.utc) if date.tzinfo is None else date
    except (AttributeError, ValueError, TypeError):
        return None


def date_days(query):
    return query.posted_within_days or {"24hr": 1, "past_week": 7, "past_month": 30}.get(query.date_since_posted)


def unsupported_filters(query, extra=()):
    names = [key for key in ("salary", "experience_level", "has_verification", "under_10_applicants", *extra) if getattr(query, key)]
    if names:
        raise ProviderError("unsupported_filter", "This source cannot apply these filters: " + ", ".join(names) + ". Clear them to search.")


def _matches(job, query, now=None, *, keywords=True, location=True):
    haystack = f"{job.title} {job.company} {job.description or ''}".casefold()
    # The pipeline emits quoted title alternatives joined with OR.
    groups = re.split(r"\s+OR\s+", query.keywords)
    alternatives = [[phrase or word for phrase, word in re.findall(r'\"([^\"]+)\"|(\S+)', group)] for group in groups]
    if keywords and not any(all(term.casefold() in haystack for term in terms) for terms in alternatives):
        return False
    if location and query.location and query.location.casefold() not in (job.location or "").casefold():
        return False
    for selected, actual in ((query.workplace_type, job.workplace_type), (query.job_type, job.employment_type)):
        if selected and actual not in (selected if isinstance(selected, list) else [selected]):
            return False
    days = date_days(query)
    if days:
        date = posted_date(job.posted_at)
        if date is None or date < (now or datetime.now(timezone.utc)) - timedelta(days=days):
            return False
    return True


def make_job(*, title, company, location, url, job_id, source, description=None, posted_at=None,
             employment_type=None, workplace_type=None, salary=None):
    title, company, url = _text(title), _text(company), _text(url)
    if not title or not company or not url:
        return None
    description = plain_text(description)
    try:
        return Job(title=title, company=company, location=_text(location), application_url=url,
                   job_id=_text(job_id) or url, source=source, description=description,
                   posted_at=_text(posted_at), employment_type=employment_type, workplace_type=workplace_type,
                   salary=_text(salary))
    except ValueError:
        return None


def with_skills(jobs):
    # Extract skills only for the returned page, not every job on a large board.
    for job in jobs:
        job.skills = mentioned_skills(f"{job.title}\n{job.description or ''}")
    return jobs


class ATSProvider:
    name = "ats"
    endpoint = ""
    unsupported_options = ()

    def __init__(self, boards=None, timeout=15, retries=2, cache_ttl=900, delay=2, max_pages=8,
                 fetch_descriptions=True, *, fetch=None, sleep=None, now=None):
        self.companies = CompanyRegistry()
        default = [c.board_slug for c in self.companies.list_by_ats(self.name)]
        self.boards = tuple(dict.fromkeys(default if boards is None else boards))
        for board in self.boards:
            if not BOARD_SLUG.fullmatch(board.removeprefix("eu:") if self.name == "lever" else board):
                raise ValueError(f"Invalid {self.name} board token: {board}")
        self.max_pages, self.fetch_descriptions = max_pages, fetch_descriptions
        self.api = PublicAPI(timeout=timeout, retries=retries, delay=delay, fetch=fetch, **({"sleep": sleep} if sleep else {}))
        self.cache = JobCache(ttl=cache_ttl)
        self.now = now or (lambda: datetime.now(timezone.utc))

    def _request(self, url):
        return self.api.request(url)

    def _url(self, board):
        return self.endpoint.format(board=quote(board, safe=""))

    def _records(self, payload):
        return records(payload, "jobs")

    def _job(self, record, board):
        raise NotImplementedError

    def company_name(self, board):
        company = self.companies.get_by_board(self.name, board)
        return company.name if company else board.removeprefix("eu:").replace("-", " ")

    def search(self, query: JobSearchQuery, limit: int | None = None) -> ProviderResult:
        unsupported_filters(query, self.unsupported_options)
        limit = query.limit if limit is None else limit
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        boards = self.boards
        if query.career_url:
            match = ATSDetector.detect(query.career_url)
            if not match or match[0] != self.name:
                raise ProviderError("invalid_board", "The career URL does not belong to the selected source.")
            boards = (match[1],)
        if not boards:
            raise ProviderError("not_configured", f"No {self.name} company boards configured. Supply a career URL.")
        key = f"{boards}:{query.model_dump_json()}:{limit}"
        cached = self.cache.get(key)
        if cached is not None:
            cached.cached = True
            return cached
        jobs, warnings, failures, seen = [], [], [], set()
        pages, succeeded, malformed, missing_dates = 0, 0, 0, 0
        now = self.now()
        for board in boards[:self.max_pages]:
            pages += 1
            try:
                rows = self._records(self._request(self._url(board)))
                succeeded += 1
            except ProviderError as exc:
                failures.append(exc)
                warnings.append(f"{board}: {exc}")
                continue
            for record in rows:
                try:
                    job = self._job(record, board) if isinstance(record, dict) else None
                except (ValueError, TypeError, KeyError, AttributeError):
                    job = None
                if job is None:
                    malformed += 1
                    continue
                if date_days(query) and posted_date(job.posted_at) is None:
                    missing_dates += 1
                if job.job_id not in seen and _matches(job, query, now):
                    jobs.append(job)
                    seen.add(job.job_id)
        if malformed:
            warnings.append(f"Skipped {malformed} incomplete or invalid listings.")
        if missing_dates:
            warnings.append(f"Excluded {missing_dates} listings without a publication date. Choose Any time to include them.")
        if len(boards) > self.max_pages:
            warnings.append(f"Searched only the first {self.max_pages} configured boards (JOBS_MAX_PAGES).")
        if query.sort_by == "recent":
            jobs.sort(key=lambda job: posted_date(job.posted_at) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        start = query.page * limit
        page_jobs = with_skills(jobs[start:start + limit])
        result = ProviderResult(provider=self.name, jobs=page_jobs, returned=len(page_jobs), pages_fetched=pages,
            next_page=query.page + 1 if start + limit < len(jobs) else None,
            status="error" if not succeeded else "partial" if warnings else "ok", warnings=warnings,
            error_code=failures[0].code if not succeeded else "partial_upstream_failure" if failures else None,
            error=str(failures[0]) if not succeeded else None,
            retry_after=failures[0].retry_after if not succeeded else None)
        if succeeded and not failures:
            self.cache.set(key, result)
        return result
