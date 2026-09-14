"""LinkedIn public-listing adapter, inspired by linkedin-jobs-api.

Independent Python implementation of the reference search contract. Fixed host,
bounded requests, typed failures, and no login, proxy rotation, or bypass logic.
Reference: https://github.com/VishwaGauravIn/linkedin-jobs-api
"""
from __future__ import annotations

import json
import re
import math
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import threading
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from html import unescape
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ats_matcher.jobs.base import ProviderError
from ats_matcher.jobs.cache import JobCache
from ats_matcher.jobs.skills import mentioned_skills
from ats_matcher.schemas.jobs import Job, JobSearchQuery, ProviderResult

ENDPOINT = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
POSTING = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
VIEW = "https://www.linkedin.com/jobs/view/{job_id}"
DATE = {"past_month": "r2592000", "past_week": "r604800", "24hr": "r86400"}
TYPE = {"full_time": "F", "part_time": "P", "contract": "C", "temporary": "T", "volunteer": "V", "internship": "I"}
WORKPLACE = {"on_site": "1", "remote": "2", "hybrid": "3"}
EXPERIENCE = {"internship": "1", "entry_level": "2", "associate": "3", "senior": "4", "director": "5", "executive": "6"}
SALARY = {40000: "1", 60000: "2", 80000: "3", 100000: "4", 120000: "5"}


def build_search_url(query: JobSearchQuery, page: int | None = None) -> str:
    params = {"keywords": query.keywords, "start": 25 * (query.page if page is None else page), "sortBy": "DD" if query.sort_by == "recent" else "R"}
    if query.location:
        params["location"] = query.location
    def codes(mapping, value):
        return ",".join(mapping[item] for item in value) if isinstance(value, list) else mapping.get(value)
    date_filter = f"r{query.posted_within_days * 86400}" if query.posted_within_days is not None else DATE.get(query.date_since_posted)
    for key, value in (("f_TPR", date_filter), ("f_JT", codes(TYPE, query.job_type)), ("f_WT", codes(WORKPLACE, query.workplace_type)), ("f_E", codes(EXPERIENCE, query.experience_level)), ("f_SB2", SALARY.get(query.salary))):
        if value:
            params[key] = value
    if query.has_verification:
        params["f_VJ"] = "true"
    if query.under_10_applicants:
        params["f_EA"] = "true"
    return ENDPOINT + "?" + urlencode(params)


def build_posting_url(job_id: str) -> str:
    if not re.fullmatch(r"\d{4,20}", job_id):
        raise ProviderError("invalid_response", "LinkedIn returned an unusable job id.")
    return POSTING.format(job_id=job_id)


def build_view_url(job_id: str) -> str:
    if not re.fullmatch(r"\d{4,20}", job_id):
        raise ProviderError("invalid_response", "LinkedIn returned an unusable job id.")
    return VIEW.format(job_id=job_id)


@dataclass
class Node:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list = field(default_factory=list)

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()

    def find(self, css_class: str = "", tag: str = ""):
        return next((n for n in self.walk() if (not tag or n.tag == tag) and (not css_class or css_class in n.attrs.get("class", "").split())), None)

    def find_attr(self, name: str, value: str = "", contains: str = ""):
        for node in self.walk():
            raw = node.attrs.get(name)
            if raw is None:
                continue
            if value and raw != value:
                continue
            if contains and contains not in raw:
                continue
            return node
        return None

    def text(self) -> str:
        return " ".join(" ".join(c.text() if isinstance(c, Node) else c for c in self.children).split())


class CardParser(HTMLParser):
    def __init__(self, max_stack=100):
        super().__init__(convert_charrefs=True)
        self.root = Node("root")
        self.stack = [self.root]
        self.max_stack = max_stack

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict((k, v or "") for k, v in attrs))
        self.stack[-1].children.append(node)
        if tag not in {"img", "br", "hr", "meta", "link", "input", "source", "wbr", "area", "base", "embed", "param", "track", "col"}:
            if len(self.stack) > self.max_stack:
                raise ProviderError("invalid_response", "LinkedIn returned an unexpected page structure.")
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)

    def handle_comment(self, data):
        # Guest pages hide the company apply URL in an HTML comment inside <code id="applyUrl">.
        if self.stack[-1].tag == "code":
            self.stack[-1].children.append(data)


def parse_job_cards(html: str) -> tuple[list[Job], int]:
    if not html.strip():
        return [], 0
    parser = CardParser()
    parser.feed(html)
    root = parser.root
    cards = [n for n in root.walk() if "base-search-card" in n.attrs.get("class", "").split()]
    if not cards:
        cards = [n for n in root.walk() if n.tag == "li" and n.find("base-search-card__title")]
    if not cards:
        lower = html.lower()
        if any(marker in lower for marker in ("authwall", "challenge", "security verification", 'name="session_key"')):
            raise ProviderError("access_blocked", "LinkedIn requires verification or sign-in. Try again later or choose another source.")
        if any(marker in lower for marker in ("no-results", "no results", "no matching jobs")):
            return [], 0
        raise ProviderError("invalid_response", "LinkedIn returned a page without recognizable job cards. Its page format may have changed.")
    jobs, skipped = [], 0
    for card in cards:
        title, company, link = card.find("base-search-card__title"), card.find("base-search-card__subtitle"), card.find("base-card__full-link")
        try:
            raw_url = urljoin("https://www.linkedin.com", link.attrs.get("href", "")) if link else ""
            parts = urlsplit(raw_url)
        except ValueError:
            skipped += 1
            continue
        job_id = re.search(r"(?:/|\-)(\d+)/?$", parts.path)
        if not title or not title.text() or not company or not company.text() or parts.scheme != "https" or not parts.hostname or not (parts.hostname == "linkedin.com" or parts.hostname.endswith(".linkedin.com")) or not parts.path.startswith("/jobs/view/") or not job_id or parts.username or parts.password:
            skipped += 1
            continue
        def field_text(css):
            node = card.find(css)
            return node.text() if node and node.text() else None
        date, image = card.find(tag="time"), card.find("artdeco-entity-image")
        logo = None
        if image:
            for candidate in (image.attrs.get("data-delayed-url"), image.attrs.get("src")):
                try:
                    if candidate:
                        Job.web_urls_only(candidate)
                        logo = candidate
                        break
                except ValueError:
                    continue
        try:
            apply = _apply_fields(card)
            jobs.append(Job(title=title.text(), company=company.text(), location=field_text("job-search-card__location"), posted_at=date.attrs.get("datetime") if date else None, posted_relative=date.text() if date and date.text() else None, salary=field_text("job-search-card__salary-info"), company_logo=logo, application_url=urlunsplit((parts.scheme, parts.netloc, parts.path, "", "")), job_id=job_id.group(1), source="linkedin", **apply))
        except ValueError:
            skipped += 1
    if not jobs and skipped:
        raise ProviderError("invalid_response", "LinkedIn returned job cards without usable titles, companies, or listing links.")
    return jobs, skipped


BLOCK_TAGS = {"p", "div", "section", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "tr"}
SKIP_TAGS = {"script", "style", "button", "svg", "noscript"}
INSIGHT_KEYS = ("jobInsight", "topCardInsight", "jobDetailsInsight", "workplaceType", "employmentType")
EMPLOYMENT_LABELS = {
    "full-time": "full_time",
    "full time": "full_time",
    "part-time": "part_time",
    "part time": "part_time",
    "contract": "contract",
    "contractor": "contract",
    "temporary": "temporary",
    "internship": "internship",
    "intern": "internship",
    "volunteer": "volunteer",
}
WORKPLACE_LABELS = {"on-site": "on_site", "on site": "on_site", "onsite": "on_site", "remote": "remote", "hybrid": "hybrid"}
LD_WORKPLACE_LABELS = {**WORKPLACE_LABELS, "telecommute": "remote", "tele commute": "remote"}
EASY_APPLY_LABELS = {
    "easy apply",
    "eenvoudig solliciteren",
    "einfache bewerbung",
    "candidature simplifiée",
    "candidature simplifiee",
    "solicitud sencilla",
    "candidatura simplificada",
    "candidatura rapida",
}
APPLY_HINT_CLASSES = {
    "job-search-card__easy-apply-label",
    "result-benefits__text",
    "result-benefits",
    "job-posting-benefits",
    "apply-button",
    "jobs-apply-button",
}


def _linkedin_host(hostname: str | None) -> bool:
    host = (hostname or "").lower()
    return host == "linkedin.com" or host.endswith(".linkedin.com")


def _external_apply_url(value: str | None) -> str | None:
    if not value:
        return None
    text = unescape(unquote(value)).strip()
    text = re.sub(r"^<!--+|--+>$", "", text).strip()
    if not text:
        return None
    try:
        parsed = urlsplit(text)
    except ValueError:
        return None
    if _linkedin_host(parsed.hostname):
        wrapped = dict(parse_qsl(parsed.query)).get("url") or dict(parse_qsl(parsed.query)).get("session_redirect")
        return _external_apply_url(wrapped)
    try:
        Job.web_urls_only(text)
    except ValueError:
        return None
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, ""))


def _apply_fields(root: Node) -> dict:
    found: dict = {}
    for node in root.walk():
        if node.tag == "code" and node.attrs.get("id") == "applyUrl":
            url = _external_apply_url(node.text())
            if url:
                found["external_apply_url"] = url
                found["easy_apply"] = False
        tracking = f"{node.attrs.get('data-tracking-control-name', '')} {node.attrs.get('data-control-name', '')}".lower()
        if "easy_apply" in tracking or "easy-apply" in tracking or "easyapply" in tracking:
            found.setdefault("easy_apply", True)
        elif "offsite" in tracking:
            found.setdefault("easy_apply", False)
        classes = set(node.attrs.get("class", "").split())
        if classes & APPLY_HINT_CLASSES or any("easy-apply" in item for item in classes):
            label = _normalized_label(node.text())
            if label in EASY_APPLY_LABELS or label.startswith("easy apply"):
                found.setdefault("easy_apply", True)
    if found.get("external_apply_url"):
        found["easy_apply"] = False
    return found


def node_text(node: Node) -> str:
    chunks: list[str] = []

    def walk(current: Node) -> None:
        for child in current.children:
            if isinstance(child, str):
                chunks.append(child)
            elif child.tag in SKIP_TAGS:
                continue
            elif child.tag == "br":
                chunks.append("\n")
            elif child.tag == "li":
                chunks.append("\n• ")
                walk(child)
                chunks.append("\n")
            elif child.tag in BLOCK_TAGS:
                chunks.append("\n")
                walk(child)
                chunks.append("\n")
            else:
                walk(child)

    walk(node)
    text = re.sub(r"[ \t]+", " ", "".join(chunks))
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()[:20000]


def _criterion(item: Node) -> tuple[str, str]:
    header = item.find("description__job-criteria-subheader")
    value = item.find("description__job-criteria-text")
    return ((header.text() if header else ""), (value.text() if value else ""))


def _clean_description(text: str) -> str | None:
    if text.lower().startswith("about the job"):
        text = text[13:].lstrip(" \n:-")
    text = text.strip()
    return text if len(text) >= 20 else None


def _fragment_text(html: str) -> str:
    parser = CardParser(max_stack=2000)
    parser.feed(html)
    return node_text(parser.root)


def _ld_items(payload):
    if isinstance(payload, list):
        for item in payload:
            yield from _ld_items(item)
        return
    if not isinstance(payload, dict):
        return
    yield payload
    graph = payload.get("@graph")
    if isinstance(graph, list):
        for item in graph:
            yield from _ld_items(item)


def _ld_strings(value):
    if isinstance(value, list):
        for item in value:
            yield from _ld_strings(item)
    elif isinstance(value, str) and value.strip():
        yield value


def _normalized_label(value: str) -> str:
    return " ".join(value.lower().replace("_", " ").replace("/", " ").replace("-", " ").split())


def _labels_from_text(text: str, workplaces=WORKPLACE_LABELS) -> dict:
    details = {}
    if not text:
        return details
    parts = [text, *re.split(r"[·•|,]", text)]
    for part in parts:
        choice = _normalized_label(part)
        if "employment_type" not in details and choice in EMPLOYMENT_LABELS:
            details["employment_type"] = EMPLOYMENT_LABELS[choice]
        if "workplace_type" not in details and choice in workplaces:
            details["workplace_type"] = workplaces[choice]
    return details


def _json_ld_fields(root: Node) -> dict:
    fields: dict = {}
    for node in root.walk():
        if node.tag != "script" or "ld+json" not in node.attrs.get("type", "").lower():
            continue
        raw = "".join(part for part in node.children if isinstance(part, str)).strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for item in _ld_items(payload):
            types = item.get("@type")
            if isinstance(types, str):
                types = [types]
            if not isinstance(types, list) or not any(str(kind).endswith("JobPosting") for kind in types):
                continue
            desc = item.get("description")
            if isinstance(desc, str) and "description" not in fields:
                try:
                    text = _fragment_text(desc) if "<" in desc else " ".join(desc.split())
                except ProviderError:
                    text = ""
                cleaned = _clean_description(text)
                if cleaned:
                    fields["description"] = cleaned
            for field in ("employmentType", "jobLocationType"):
                for part in _ld_strings(item.get(field)):
                    fields.update({key: value for key, value in _labels_from_text(part, LD_WORKPLACE_LABELS).items() if key not in fields})
            if isinstance(item.get("directApply"), bool) and "easy_apply" not in fields:
                fields["easy_apply"] = item["directApply"]
            if fields.get("description") and fields.get("employment_type") and fields.get("workplace_type"):
                return fields
    return fields


def _json_ld_description(root: Node) -> str | None:
    return _json_ld_fields(root).get("description")


def _insight_labels(root: Node) -> dict:
    skip = set()
    for marker in (
        root.find_attr("data-sdui-component", contains="aboutTheJob"),
        root.find_attr("data-testid", value="expandable-text-box"),
        root.find("show-more-less-html__markup"),
        root.find("description__text"),
    ):
        if marker:
            skip.update(id(node) for node in marker.walk())
    found: dict = {}
    for node in root.walk():
        if id(node) in skip:
            continue
        component = node.attrs.get("data-sdui-component", "")
        classes = node.attrs.get("class", "")
        if not any(key in component for key in INSIGHT_KEYS) and "job-insight" not in classes and "job-criteria" not in classes:
            continue
        text = node_text(node)
        if len(text) > 120:
            continue
        for key, value in _labels_from_text(text).items():
            found.setdefault(key, value)
    return found


def _description_from_tree(root: Node) -> str | None:
    # Logged-in job-seeker pages use SDUI attributes. Guest pages use the older classes.
    # Hashed CSS class names are not stable and are not used as selectors.
    candidates = []
    sdui = root.find_attr("data-sdui-component", contains="aboutTheJob")
    if sdui:
        candidates.append(sdui)
    box = root.find_attr("data-testid", value="expandable-text-box")
    if box:
        candidates.append(box)
    container = root.find("description__text") or root.find("description")
    markup = container.find("show-more-less-html__markup") if container else None
    if markup is None:
        markup = root.find("show-more-less-html__markup")
    if markup:
        candidates.append(markup)
    for node in candidates:
        text = _clean_description(node_text(node))
        if text:
            return text
    return _json_ld_description(root)


def parse_job_posting(html: str) -> dict:
    """Read a public posting page. Supports guest markup, job-seeker SDUI, and JobPosting JSON-LD."""
    if not html.strip():
        return {}
    parser = CardParser(max_stack=2000)
    try:
        parser.feed(html)
    except ProviderError:
        return {}
    root = parser.root
    description = _description_from_tree(root)
    details: dict = {"description": description, "skills": mentioned_skills(description or "")}
    for node in root.walk():
        if "description__job-criteria-item" not in node.attrs.get("class", "").split():
            continue
        header, value = _criterion(node)
        key = " ".join(header.lower().split())
        choice = " ".join(value.lower().replace("/", " ").split())
        if "employment" in key:
            details["employment_type"] = EMPLOYMENT_LABELS.get(choice)
        elif "workplace" in key or choice in WORKPLACE_LABELS:
            details["workplace_type"] = WORKPLACE_LABELS.get(choice)
    extras = {**_insight_labels(root), **_json_ld_fields(root)}
    apply = _apply_fields(root)
    for key in ("employment_type", "workplace_type"):
        if not details.get(key) and extras.get(key):
            details[key] = extras[key]
    if "easy_apply" not in apply and extras.get("easy_apply") is not None:
        apply["easy_apply"] = extras["easy_apply"]
    details.update(apply)
    return {key: value for key, value in details.items() if value or value is False}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def retry_after_seconds(value: str, now: datetime | None = None) -> int | None:
    value = value.strip()
    if value.isdigit():
        return int(value)
    try:
        deadline = parsedate_to_datetime(value)
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        return max(0, math.ceil((deadline - (now or datetime.now(timezone.utc))).total_seconds()))
    except (ValueError, TypeError, OverflowError):
        return None


def fetch_html(url: str, timeout: float) -> str:
    request = Request(url, headers={"User-Agent": "ATSMatcher/0.2 (public job search)", "Accept": "text/html", "Accept-Language": "en-US,en;q=0.9"})
    try:
        with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            data = response.read(2 * 1024 * 1024 + 1)
            if len(data) > 2 * 1024 * 1024:
                raise ProviderError("invalid_response", "LinkedIn returned an unexpectedly large response.")
            return data.decode("utf-8", errors="replace")
    except HTTPError as exc:
        retry_after = retry_after_seconds(exc.headers.get("Retry-After", ""))
        if exc.code == 429:
            raise ProviderError("rate_limited", "LinkedIn is limiting requests. Wait before trying again.", retry_after) from exc
        if exc.code in {301, 302, 303, 307, 308, 401, 403, 999}:
            raise ProviderError("access_blocked", "LinkedIn did not allow this public search. Try later or choose another source.") from exc
        if 500 <= exc.code < 600:
            raise ProviderError("temporarily_unavailable", "LinkedIn is temporarily unavailable.") from exc
        raise ProviderError("http_error", f"LinkedIn returned HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise ProviderError("network_error", "Could not reach LinkedIn. Check the connection and try again.") from exc


class LinkedInProvider:
    name = "linkedin"
    def __init__(self, *, timeout=15.0, delay=2.0, retries=2, max_pages=8, cache_ttl=3600, fetch=fetch_html, sleep=time.sleep, clock=time.monotonic, fetch_descriptions=True):
        self.timeout, self.delay, self.retries, self.max_pages = timeout, delay, retries, max_pages
        self.fetch, self.sleep, self.clock = fetch, sleep, clock
        self.fetch_descriptions = fetch_descriptions
        self.cache = JobCache(ttl=cache_ttl, clock=clock)
        self._lock = threading.Lock()
        self._last_request = None
        self._retry_until = 0.0

    def _fetch(self, url):
        for attempt in range(self.retries + 1):
            if self._last_request is not None:
                self.sleep(max(0, self.delay - (self.clock() - self._last_request)))
            self._last_request = self.clock()
            try:
                return self.fetch(url, self.timeout)
            except ProviderError as exc:
                if exc.code == "rate_limited":
                    wait = max(1, exc.retry_after if exc.retry_after is not None else 60)
                    self._retry_until = self.clock() + wait
                    raise ProviderError("rate_limited", f"LinkedIn is limiting requests. Try again in {wait} seconds.", wait) from exc
                if exc.code not in {"network_error", "temporarily_unavailable"} or attempt == self.retries:
                    raise
                self.sleep(min(2 ** attempt, 8))

    def _posting_urls(self, job: Job) -> list[str]:
        urls = [build_posting_url(job.job_id), build_view_url(job.job_id)]
        application = job.application_url
        if application and "/jobs/view/" in application and application not in urls:
            urls.append(application)
        return urls

    def _enrich_descriptions(self, result: ProviderResult) -> None:
        if not self.fetch_descriptions or not result.jobs:
            return
        fetched = 0
        for index, job in enumerate(result.jobs):
            if job.description:
                fetched += 1
                continue
            details: dict = {}
            try:
                for url in self._posting_urls(job):
                    try:
                        html = self._fetch(url)
                    except ProviderError as exc:
                        if exc.code == "rate_limited":
                            raise
                        continue
                    details = parse_job_posting(html)
                    if details.get("description"):
                        break
            except ProviderError as exc:
                if exc.code == "rate_limited":
                    result.status = "partial"
                    result.error_code, result.error, result.retry_after = exc.code, str(exc), exc.retry_after
                    result.warnings.append(f"Stopped reading descriptions after {index} listings because LinkedIn is limiting requests.")
                    break
                continue
            if not details:
                continue
            result.jobs[index] = job.model_copy(update=details)
            if details.get("description"):
                fetched += 1
        missing = len(result.jobs) - fetched
        if fetched == 0:
            result.warnings.append("Job descriptions were not available from LinkedIn for this search.")
            if result.status == "ok":
                result.status = "partial"
        elif missing:
            result.warnings.append(f"Read descriptions for {fetched} of {len(result.jobs)} listings.")

    def search(self, query: JobSearchQuery, limit: int | None = None) -> ProviderResult:
        if limit is not None:
            query = JobSearchQuery.model_validate({**query.model_dump(), "limit": limit})
        key = query.model_dump_json()
        with self._lock:
            cached = self.cache.get(key)
            if cached is not None:
                cached.cached = True
                return cached
            wait = math.ceil(self._retry_until - self.clock())
            if wait > 0:
                return ProviderResult(provider=self.name, status="error", error_code="rate_limited", error=f"LinkedIn is limiting requests. Try again in {wait} seconds.", retry_after=wait, next_page=query.page)
            result = ProviderResult(provider=self.name)
            seen = set()
            for offset in range(self.max_pages):
                try:
                    html = self._fetch(build_search_url(query, query.page + offset))
                    jobs, skipped = parse_job_cards(html)
                except ProviderError as exc:
                    result.status = "partial" if result.jobs else "error"
                    result.error_code, result.error, result.retry_after = exc.code, str(exc), exc.retry_after
                    result.next_page = query.page + offset
                    result.returned = len(result.jobs)
                    if result.jobs:
                        self._enrich_descriptions(result)
                    return result
                result.pages_fetched += 1
                if skipped:
                    result.warnings.append(f"Skipped {skipped} incomplete job cards on page {query.page + offset}.")
                if not jobs:
                    break
                new = [j for j in jobs if j.job_id not in seen]
                # Deduplicate within this batch as well as across pages.
                for job in new:
                    if job.job_id not in seen:
                        result.jobs.append(job)
                        seen.add(job.job_id)
                if not new:
                    result.warnings.append("LinkedIn repeated a page; stopped to avoid duplicate requests.")
                    break
                if len(result.jobs) >= query.limit:
                    result.jobs = result.jobs[:query.limit]
                    result.next_page = query.page + offset + 1
                    break
            else:
                result.next_page = query.page + self.max_pages
                result.warnings.append("Reached the per-search page limit. Continue with next_page for more results.")
            result.returned = len(result.jobs)
            if result.jobs:
                self._enrich_descriptions(result)
            if result.warnings and result.status == "ok":
                result.status = "partial"
            # Do not cache blocked, failed, or incomplete searches.
            if result.status == "ok":
                self.cache.set(key, result)
            return result
