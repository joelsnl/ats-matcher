# Job search: one interface, multiple sources

LinkedIn is the first implemented channel. This is an independent Python implementation
informed by [linkedin-jobs-api](https://github.com/VishwaGauravIn/linkedin-jobs-api),
particularly its public search filters, 25-position page offsets, and job-card fields.
It uses LinkedIn's public guest-search pages, not an official or authenticated API.
There is no Node dependency, login automation, proxy rotation, or verification bypass.

## Structure

```text
CLI / local app HTTP API / live-search screen
  -> JobSearchQuery (shared, validated options)
  -> JobSearchService (select sources, merge, deduplicate, report failures)
  -> ProviderRegistry (one factory per channel)
      -> LinkedInProvider (source filters, paging, HTML parsing)
      -> GreenhouseProvider / LeverProvider / AshbyProvider (company boards)
      -> FreehireProvider / IndeedProvider (catalogue search)
  -> JobSearchResponse (normalized jobs + per-source status)
```

- `jobs/base.py`: provider protocol and meaningful provider errors.
- `jobs/providers/linkedin.py`: LinkedIn-only URL mapping and page parsing.
- `jobs/cache.py`: bounded, thread-safe TTL cache, with independent result copies.
- `jobs/registry.py`: lazy provider registration and reuse.
- `jobs/service.py`: multiple sources and consistent results.
- `schemas/jobs.py`: provider-neutral query, listing, and status definitions.

## Search from the command line

```powershell
ats-match providers
ats-match search --keyword "software engineer" --location "Berlin, Germany" --workplace remote --date past_week --limit 15
ats-match search --keyword "data analyst" --experience "entry level" --job-type "full time" --sort recent --page 1 --verified --under-10-applicants --out jobs.json
ats-match search --keyword "engineer" --job-type "part_time,internship" --workplace "remote,hybrid" --experience "entry_level,associate" --days 3
ats-match match --profile cv.json --location Berlin --jobs 15 --out matches.json
ats-match run --cv resume.pdf --rules-only --keyword "software engineer" --location Berlin --out matches.json
```

`match` uses an existing search query, otherwise up to three suggested/recent titles
joined with OR. `--keyword` overrides them. Basic extraction does not infer titles,
so use an explicit keyword. GitHub enrichment remains unimplemented but does not block
job search. Only search terms and filters go to the job source, not the CV itself.

Exit codes: 0 = successful search (possibly no results); 1 = all sources failed;
2 = partial results or a CLI validation error. Inspect `jobs_meta` for details.

## Local API and browser

Run `python -m ats_matcher.server --port 8766` or `ats-match serve --port 8766`, then open
http://127.0.0.1:8766/#live. The Live job search screen supports all query filters.
After changing Python code, stop the local server with Ctrl+C and start it again on
the same port, then reload the browser. HTML and JavaScript are read from disk on each
request, but Python code is loaded at startup. An old server can therefore show the
new multi-select form while rejecting its lists. Work-arrangement values are already
case-insensitive: `On-Site`, `ON SITE`, and `on_site` are accepted, alone or in a list.

Live results replace the daily shortlist. Saving a listing adds it to My applications.
Listings link to their original source page. This app does not submit applications.

- `GET /api/providers`: registered, implemented channels.
- `POST /api/jobs`: search options, plus an optional `providers` list.
- HTTP 200: success or partial results; 400: invalid input; 502: all sources failed.
- Same localhost protections as CV upload. Requests are limited to 16 KB.

```json
{
  "keyword": "software engineer",
  "location": "Berlin",
  "dateSincePosted": "past week",
  "jobType": "full time",
  "remoteFilter": "remote",
  "experienceLevel": "senior",
  "sortBy": "recent",
  "limit": 15,
  "page": 0,
  "has_verification": false,
  "under_10_applicants": false,
  "providers": ["linkedin"]
}
```

## Reference compatibility

| Reference input | Canonical Python field |
| --- | --- |
| keyword | keywords |
| dateSincePosted | date_since_posted |
| postedWithinDays (extension) | posted_within_days |
| jobType | job_type |
| remoteFilter | workplace_type |
| experienceLevel | experience_level |
| sortBy | sort_by |
| location, salary, limit, page, has_verification, under_10_applicants | Same names |

Spaces/hyphens in option values are normalized: `full time` and `full-time` become
`full_time`. Job type, work arrangement, and experience accept a single string,
a nonempty array, or comma-separated values. For example, `"remoteFilter": ["remote", "hybrid"]`
requests either arrangement. Omit a filter (or use null) for any value; empty arrays
and unknown values are rejected. Multiple selections are normalized and deduplicated.

`24h` and `24hr` both request the last 24 hours. `posted_within_days` (or
`postedWithinDays`) accepts a whole number from 1 to 365 and overrides the date preset.
The CLI exposes this as `--days`; the browser has a "Choose number of days" option.
These filters are sent to LinkedIn; publication dates are not independently verified.

Legacy `f_TPR`, `f_E`, and `f_WT` profile filters are translated on load.
Salary bands are 40000, 60000, 80000, 100000, 120000; availability and currency depend
on LinkedIn's market. Verification and applicant-count filters are forwarded to
LinkedIn, not independently verified by this tool.

Output mapping: `position` -> `title`, `companyLogo` -> `company_logo`, `date` ->
`posted_at`, `agoTime` -> `posted_relative`, `jobUrl` -> `application_url`.
`company`, `location`, and `salary` retain their meaning. Every listing also has
`source` and `job_id`. Missing values stay null. Search cards still omit the full
description; that text is read from each public posting page when description
fetching is enabled. Skill names found in that text are listed for overlap matching.
They are not treated as a verified requirements list or an ATS score.
`application_url` is the observed job-listing link, not necessarily a direct employer
application endpoint. Tracking parameters are removed from LinkedIn listing links.

After the search cards, the adapter requests each public guest posting page
(`jobs-guest/jobs/api/jobPosting/{id}`), then the public `/jobs/view/{id}` page if
that guest response has no description. Guest pages keep the full text in
`show-more-less-html__markup` (“Show more” only unclamps CSS). Logged-in job-seeker
pages use SDUI attributes instead (`data-sdui-component` containing `aboutTheJob`,
and `data-testid="expandable-text-box"`). Hashed CSS class names are ignored.
JobPosting JSON-LD is a last resort. Descriptions, recognized skill names, and
employment/workplace criteria are copied onto the listing. Sign-in chrome is ignored
when description markup is present. Set `JOBS_FETCH_DESCRIPTIONS=false` to skip these
extra requests.

Matching covers related tools, not only identical names: GitHub Actions, Jenkins,
or GitLab CI/CD counts as CI/CD. Generic posting language such as Communication is
ignored. Sibling products are not treated as the same tool (Docker is not Kubernetes,
AWS is not Azure). It is not an ATS score. The browser shortlist orders live results
by this coverage; `ats-match match` and `ats-match run` do the same.

Cover letters: `POST /api/cover-letter` with the browser profile and listing text.
The local model writes a short note from those facts. It needs `--mode cpu` or
`--mode gpu`. Generic posting language is ignored in matching. Missing tools
from the listing must be named as gaps; the letter must not invent employers,
teams, or tools the profile does not have.

Interview prep: `POST /api/interview-prep` with the same profile and listing
payload. Open-source docs and guides are matched to the posting even in
`--mode basic`. Story prompts from the person's own work need `--mode cpu` or
`--mode gpu`. The pack is not a generated syllabus.

Intentional differences from the reference: keyword is required; limit is bounded
1-100 rather than unlimited; host cannot be overridden; failures remain visible;
no randomized user agents; partial/blocked searches are not cached. Page `n` starts
at upstream offset `n * 25`. If limit truncates a page, the next page advances to the
next source offset, not the next unseen individual item. Results can change upstream.

## Error handling and limits

The upstream README's [Our Sponsor section](https://github.com/VishwaGauravIn/linkedin-jobs-api#our-sponsor)
advertises 300 requests/minute for Proxycurl's profile-data service. That figure does
not describe the public LinkedIn jobs endpoint used here. The README supplies no
numeric request quota for that endpoint (reviewed 2026-09-12).

Our two-second request spacing and 60-second fallback pause are local pacing
and recovery choices, not published LinkedIn quotas or guaranteed safe thresholds.
`JOBS_REQUEST_DELAY` controls spacing; the fallback pause is currently fixed in the
adapter. When supplied, `Retry-After` determines the pause instead. The README's
`limit` option counts returned jobs, not permitted requests per minute.

- Per-request timeout, bounded retries only for network/5xx failures.
- Rate limits, sign-in/verification responses, and redirects stop the search.
- A 429 pauses new requests across queries in the same provider instance. It honors
  numeric and HTTP-date `Retry-After` headers (minimum 1 second), or waits 60 seconds
  when no valid header is supplied. Cached results remain available during this pause.
  Separate CLI invocations/processes do not share the pause or cache.
- If a later page fails, earlier results are kept and status is `partial`.
- Repeated pages stop pagination; incomplete cards are skipped with warnings.
- An unrecognized nonempty HTML response is an error, not a fake empty success.
- Complete searches cache for one hour by default; query, page, and limit are in the key.
- Cache is process-local and does not survive restarts.
- Sources are searched in selected order. Results are deduplicated by source/id and
  canonical URL, then limited globally. Cross-source relevance ranking is not implemented.

Settings: `JOBS_PROVIDER` is a comma-separated list of registered sources (see
[provider configuration](../README.md#additional-job-sources)), `JOBS_TIMEOUT=15`, `JOBS_REQUEST_DELAY=2`, `JOBS_RETRIES=2`,
`JOBS_MAX_PAGES=8`, and `JOBS_CACHE_TTL=3600`. A source may still return fewer results
than requested or ignore a filter. Large searches can take longer due to pacing.

## Add another channel

Implement a provider with `name` and `search(query, limit=None) -> ProviderResult`.
Return normalized `Job` objects containing real source links. Put source-specific
filter translation and unsupported-filter warnings inside that provider.
Register its factory in `default_registry()`; it then becomes available to the CLI
and API without changing their search contract. The browser discovers registry entries
from `/api/providers`; its initial UI selects one source at a time, while CLI/API allow
multiple sources.

Use `ProviderError` for expected upstream failures. Avoid sending profile contact
information to a source. Tests use synthetic HTML and fake providers; live checks are
explicit and should be kept small.

## Reference provenance

The implementation was written in Python for this project; no upstream JavaScript
was vendored and no npm dependency was added. The reference repository
`VishwaGauravIn/linkedin-jobs-api` was reviewed for behavior. Its LICENSE file says
Apache-2.0 while its package metadata says MIT; consult the source license before
copying upstream code in future changes.

## Upstream issue review

See [the issue-by-issue review](upstream-issue-review.md) for fixes, regression coverage,
and source limitations from all nine upstream issues reviewed on 2026-09-12.
