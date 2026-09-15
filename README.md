# ATS Matcher

Local CV reader and multi-source job matcher. Parse a resume with optional **llama.cpp**, search **public job listings**, compare them with your actual skills (including related tools), and keep applications, cover-letter drafts, and interview prep in a browser workspace on localhost.

Version **0.2.0**. GitHub enrichment is still unimplemented. This is a loopback development app, not a production deployment and not an ATS score.

## What it does

- **Parse** PDF, Word, or text CVs into structured JSON (`full_name`, skills, titles, employers, location, …). Age is omitted unless you pass `--include-age` and the CV states it.
- **Search** LinkedIn, Greenhouse, Lever, Ashby, Freehire, and optionally Indeed from the CLI or browser. Filter support varies by source. LinkedIn supports: Keyword, location, date window (including custom 1–365 days), job type, work arrangement, salary band, experience, sort, pagination, verification, and under-10-applicants filters. Multiple types/arrangements/levels can be combined.
- **Read public posting pages** for the full description when search cards are thin. Non-English descriptions can be translated with Google Translate (default English).
- **Match** listings to a profile. Related tools count (GitHub Actions / Jenkins / GitLab CI/CD cover CI/CD). Generic posting language such as Communication is ignored. Sibling products are not equated (Docker is not Kubernetes; AWS is not Azure).
- **Browser workspace** (localhost): live shortlist, save/pass, application stages and notes, evidence comparison, cover letters, role-specific practice, dark/light theme. Progress stays in this browser.
- **Cover letters** from the local model: use your CV and real examples, choose tone, length and language, edit an autosaved draft, check claims, and save or download a version. Employer/client relationships stay explicit; search preferences are not career facts.
- **Interview practice** per listing: a focused queue of foundations, refreshers, and people-skill rehearsals, with exercises, self-checks and saved answers. The core learning plan works without a model. Local AI can tailor one exercise or give feedback grounded in exact quotes from your attempt.

It does **not** apply for you, send mail, charge money, scrape private/logged-in LinkedIn, bypass verification, or invent job URLs.

## Requirements

- Python 3.11+
- A GGUF instruct model for AI parse, cover letters, and interview story prompts (`--rules-only` / `--mode basic` skip the model)
- Network access for live job search and optional description translation

## Install

```bash
cd ats-matcher
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -e ".[dev]"
```

### Local LLM (`llama-cpp-python`)

`pip install -e ".[llm]"` downloads a **source tarball** and tries to compile. That fails on Windows unless Visual Studio C++ tools are installed.

Use a **prebuilt wheel** instead (no compiler):

```powershell
ats-match setup-llm --backend cpu       # default
ats-match setup-llm --backend vulkan    # RTX / AMD / Intel GPU on Windows
ats-match setup-llm --backend cuda      # NVIDIA CUDA 12.4 wheel
```

Equivalent pip (CPU):

```powershell
pip install --only-binary=:all: --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu llama-cpp-python==0.3.35
```

`--only-binary=:all:` is important: without it, pip may still fall back to compiling from PyPI.

## Download a model

Recommended: **Qwen3-8B** Q4_K_M (~5 GB). Same size class as Qwen2.5-7B, stronger instruction following for cover letters and CV JSON. Fits an RTX 4070-class GPU with `--mode gpu`.

```powershell
hf download bartowski/Qwen_Qwen3-8B-GGUF Qwen_Qwen3-8B-Q4_K_M.gguf --local-dir .models
```

Older fallback: **Qwen2.5-7B-Instruct** Q4_K_M (~4.7 GB). The official `Qwen/Qwen2.5-7B-Instruct-GGUF` repo splits that file into two shards. Use a single-file community quant:

```powershell
hf download bartowski/Qwen2.5-7B-Instruct-GGUF Qwen2.5-7B-Instruct-Q4_K_M.gguf --local-dir .models
```

Weaker machines: `Qwen2.5-7B-Instruct-Q3_K_M.gguf` from the 7B repo.

Then set the path, or leave it unset if a `.gguf` is already in `.models` / `models` (a `Q4_K_M` file is preferred):

```powershell
$env:LLAMA_MODEL_PATH = "$PWD\.models\Qwen_Qwen3-8B-Q4_K_M.gguf"
```

Copy [`.env.example`](.env.example) to `.env` for `LLAMA_*` and `JOBS_*` settings. CLI `--model` overrides the env path.

## Local app

This is the main UI: static files in `app/` served by a loopback HTTP server. Start it from this checkout (needed for CV upload, live search, letters, and interview prep):

```powershell
python -m ats_matcher.server                 # AI on CPU (default)
python -m ats_matcher.server --mode gpu      # AI on GPU
python -m ats_matcher.server --mode basic    # no model: CV fields, search, learning plans, manual letter checks
ats-match serve                              # same server via the CLI
```

Open **http://127.0.0.1:8765**. Stop with Ctrl+C. `--mode cpu` and `--mode gpu` will not start without a GGUF. Use `--port 8766` if needed. `python -m ats_matcher.prototype` still works as an alias.

Opening `app/index.html` as a file still loads the chrome, but live search, PDF/Word parse, cover letters, and interview packs need the local server.

### Workspace

- **Daily shortlist** — your latest live search, ordered by overlapping experience (related tools count).
- **Live job search** — the same filters as the CLI. Results replace the shortlist; saved applications are kept.
- **My applications** — stages (Saved / Applied / Interview / Closed), notes, next-step dates. Listings are snapshots and may later close.
- **Interview practice** — learning plans for saved roles plus quick warm-ups. Open a session, attempt the exercise, check your reasoning, and record a reflection. Answers and progress are saved locally.
- **My profile** — name, desired roles, skills, preferred location, description language and weekly goal. Add real achievements and review the CV text used for writing and practice. Import a CV or `ats-match parse` JSON.

On a listing you can compare skills, paste a missing description, write a cover letter, and build interview prep. Apply on the original website; this app never submits an application.

Automatic cover-letter drafting, passage revisions, tailored exercises and AI feedback need `--mode cpu` or `--mode gpu`. Learning plans, self-guided sessions and manual letter checks also work in `--mode basic`. Re-import the CV if an older browser profile is missing employers, or add CV text and examples in My profile. See [Application workflows](#application-workflows) below.

Profile, notes, letters, and drafts stay in **this browser**. They are not synced across browsers or between `file://` and localhost. **My profile → Export my workspace** writes a private JSON backup. **Restore a backup** previews and replaces the workspace, preserving a downloadable pre-restore recovery copy. Workspace backups have a separate importer from CV files and are limited to 10 MB. Reset clears the current workspace and pre-restore recovery copy. CV uploads are ≤ 5 MB and deleted after reading. Daily reminder times are stored only; this app does not send notifications.

### Application workflows

- **Bring any listing:** use **My applications → Add a listing link** or the equivalent button in Live job search. Paste the original URL, title, company, and full description. No page is fetched. Existing URLs, including links differing only in UTM tracking parameters or fragments, reopen the existing application without replacing notes or drafts.
- **Collect useful evidence:** in the letter editor, choose **Answer a few useful questions**. The app identifies up to three unevidenced requirements. Record the setting, your own actions, and an optional outcome; confirm the example is real before saving it to your profile. Motivation is saved separately for that application and does not become evidence of experience. Full example storage produces a visible error rather than discarding earlier examples.
- **Revise a passage:** select 20–2,000 characters in the letter and request simpler wording, a closer connection to the role, or a shorter version. Compare the suggestion with the original, then explicitly accept it. Only the selection changes; a previous version is saved. New claims detected by the existing heuristic checks cause rejection. These checks are incomplete, so review the suggested wording yourself.
- **Choose a practice level:** answer the warm-up before reading the notes, then open **Find my starting level**. Your self-report of explaining and applying the idea selects a foundation session or refresher; it is not an objective proficiency test. A different exercise keeps earlier answers, warm-ups and reflections in Previous attempts.
- **Return to the right practice:** record how much help you needed. Another attempt schedules tomorrow, some help schedules three days, and independent recall starts at seven days and extends up to thirty days. Repeated completion on the same day does not increase the interval. The daily shortlist and practice page surface due reviews and application follow-ups; no notification is sent. Closed applications are excluded.
- **Target the next exercise:** tailored variations include your previous reflection and the unfinished next steps from model feedback as a learning focus. They remain suggestions; the model can miss details, and code is not executed.

Run the regression checks with:

```powershell
python -m pytest -q
node --test tests/jobs-store.test.cjs tests/desk-logic.test.cjs
# Start a separate --mode basic server on port 8881 for isolated browser checks:
node tests/browser-workspace.cjs http://127.0.0.1:8881
node tests/browser-coaching.cjs http://127.0.0.1:8881
node tests/browser-desk.cjs http://127.0.0.1:8881
```

For repeatable model comparisons, `scripts/evaluate_coaching.py` submits fictional cases to a local running server. It saves outputs, timings and human review criteria, not an automatic quality ranking. Reports are written after each case, so completed cases survive a later failure. The full run includes English/Dutch letters, a passage revision, a foundation session, a refresher and a people-skill exercise. It can take several minutes on CPU.

```powershell
python scripts/evaluate_coaching.py --url http://127.0.0.1:8879 --label my-model --output .cache/model-report.json
# Or run one case:
python scripts/evaluate_coaching.py --url http://127.0.0.1:8879 --case revision
```

After changing Python, restart the server. HTML and JavaScript are reread from disk on each request.

## CLI

```bash
ats-match parse --cv path\to\resume.pdf --out cv.json
ats-match parse --cv path\to\resume.pdf --rules-only --out cv.json

ats-match search --keyword "software engineer" --location "Amsterdam, Netherlands" --workplace remote --date past_week --limit 15
ats-match search --keyword "engineer" --job-type "part_time,internship" --workplace "remote,hybrid" --days 3
ats-match providers

ats-match match --profile cv.json --out matches.json
ats-match run --cv path\to\resume.pdf --keyword "platform engineer" --location Amsterdam --out report.json

ats-match enrich --profile cv.json    # not implemented
ats-match setup-llm --backend vulkan
```

`match` searches from suggested/recent titles (OR), or `--keyword`. `--rules-only` parse does not infer titles, so pass a keyword. Only search terms and filters go to the selected source, not the CV file. Location from a parsed profile is normalized to `City, Country` when possible.

Search exit codes: 0 = ok (including zero hits), 1 = all sources failed, 2 = partial results or a validation error. Inspect `jobs_meta`.

## Additional job sources

Choose a source in **Live job search**, pass `--provider`, or set `JOBS_PROVIDER`
(comma-separated sources for the CLI/API). A provider searches only its own catalogue.

| Source | Scope and requirements |
| --- | --- |
| LinkedIn | Public guest search; default source. |
| Greenhouse | Configured company boards; Stripe is the bundled example. |
| Lever | Configured company boards; Spotify is the bundled example. EU boards are supported. |
| Ashby | Configured company boards; OpenAI is the bundled example. |
| Freehire | Public catalogue search; availability depends on upstream access controls. |
| Indeed | Optional `python-jobspy` integration; install with `pip install -e ".[indeed]"`. |

For a specific company, select its ATS source and paste its hosted **Company career URL**
in the browser. The CLI can detect the source automatically:

```powershell
ats-match search --keyword engineer --career-url https://boards.greenhouse.io/stripe --date any
ats-match search --keyword engineer --provider greenhouse,lever --date any
```

`career_url` is also accepted by `POST /api/jobs`. If `providers` is supplied alongside
it, it must contain only the matching source. URLs are parsed locally; the app requests
only the supported provider API, never an arbitrary supplied page. Detection of other
ATS hosts does not imply search support for those systems.

Configure board tokens in `.env` using `JOBS_GREENHOUSE_BOARDS`, `JOBS_LEVER_BOARDS`,
and `JOBS_ASHBY_BOARDS` (comma-separated). For EU Lever use `eu:company-token`.
Omitting a setting uses the bundled example; an empty value disables its default boards.
A career URL overrides the configured boards for that search. Company tokens and ATS
vendors can change; stale boards produce explicit failures. The packaged company CSV
is a small example catalogue, not a directory of all employers.

Set `JOBS_INDEED_COUNTRY=germany` (or another JobSpy country name) for Indeed; its default
is `usa`. JobSpy manages its own HTTP timeouts, pacing, and retries, independently of
`JOBS_TIMEOUT`, `JOBS_REQUEST_DELAY`, and `JOBS_RETRIES`. The optional dependency is
loaded only when Indeed is selected. No proxy configuration is supplied.

### Filter and paging behavior

- LinkedIn-only salary bands, experience levels, verification, and applicant-count
  filters are disabled in the browser for other sources. CLI/API requests using them
  return an actionable error instead of silently ignoring them.
- Company boards apply keywords, location, dates, job type, and work arrangement locally.
  Quoted titles joined with `OR` from profile matching are supported. Location is a
  substring of the actual listing location: try `Berlin` instead of `Berlin, Germany`
  if the source only publishes a city. Unknown type/arrangement values do not pass filters.
- A date filter excludes jobs without a known publication date; **Any time** includes
  them. Edit timestamps are never substituted for publication dates. Warnings report
  missing dates and malformed listings. Greenhouse does not expose standard job type or
  work arrangement fields; those filters are disabled for Greenhouse.
- Company-board **Most recent** sorts all matched jobs from the scanned boards before
  paging. Relevance preserves source order. At most `JOBS_MAX_PAGES` boards are requested,
  with a visible warning if that truncates the configured catalogue.
- LinkedIn pages use 25-position offsets. Other sources use `page * limit`; keep the
  maximum results value unchanged when following **Next source page**. Public catalogues
  can change between requests.
- Freehire uses its search endpoint and checks for ignored parameters. Its location
  filter applies within each source page. Indeed applies job type and remote filters
  within each page and can sort that page by date. Both can return fewer matches than
  the page size; **Next source page** continues where supported. Freehire does not
  support temporary/volunteer filters; Indeed cannot distinguish hybrid from on-site.
- HTTP failures and malformed responses are reported as errors or partial results.
  A valid empty catalogue is a successful empty search. Failed board requests are not
  cached as successful empty results. Retries honor bounded `Retry-After` delays.

Adapter contracts: [Greenhouse Job Board API](https://docs.greenhouse.io/job-board.html),
[Lever postings API](https://github.com/lever/postings-api),
[Ashby public postings](https://developers.ashbyhq.com/docs/public-job-posting-api),
[Freehire API](https://freehire.me/docs/api), and [JobSpy](https://github.com/speedyapply/JobSpy).

## Job search and public LinkedIn pages

LinkedIn remains the default channel. Its Python adapter is informed by
[linkedin-jobs-api](https://github.com/VishwaGauravIn/linkedin-jobs-api)
(public filters, 25-item page offsets, job-card fields). There is no Node dependency and no official LinkedIn API.

It requests **unauthenticated guest job pages** a browser can open without signing in. It does not log in, store LinkedIn passwords, rotate proxies, or bypass verification walls.

Requests are paced with `JOBS_REQUEST_DELAY`, bounded retries, and `Retry-After`.
See [request limits](docs/job-search.md#error-handling-and-limits) and the
[upstream issue review](docs/upstream-issue-review.md).

Architecture, filters, caching, and how to add a source: [docs/job-search.md](docs/job-search.md).

## Matching, letters, and prep

Coverage is overlap with your profile, not a hiring score. The language model never invents job URLs.

Cover-letter drafts must not claim unevidenced tools, projects or outcomes. Missing from a CV means unknown, not proof that someone has never used a tool. Add a real example if the comparison misses something. Automated checks flag unsupported tools, numbers, certain ungrounded outcomes and template output; they cannot verify every claim. Check the draft before sending.

The learning plan starts with up to three unevidenced technical skills, two refreshers and two people-skill rehearsals. Each session has a concept, warm-up, exercise, self-checks and an interview-transfer note. Curated documentation supports the exercises; a model cannot replace those links. Optional AI feedback quotes the attempted answer and does not assign a hiring score. Completing practice never adds skills to your CV.

## Tests

```bash
pytest
```

Golden-set LLM eval (requires `LLAMA_MODEL_PATH`):

```bash
pytest -m llm
# or
python -m ats_matcher.eval_extract
```

Gates: ≥90% valid JSON, ≥80% exact GitHub URL when the CV contains one. Live network searches are marked `live` and are not part of the default run.

## Project layout

```
src/ats_matcher/
  cli.py              Typer commands (including serve)
  server.py           Localhost HTTP: assets + /api/parse, /api/jobs, /api/translate, /api/cover-letter, /api/interview-prep, /api/health
  prototype.py        Thin alias for python -m ats_matcher.prototype
  pipeline.py         parse + match_jobs
  geo.py              CV location → City, Country
  extract/            PDF/DOCX/text + regex pre-extract
  llm/                llama.cpp, cover letters, interview prep
  jobs/               Search service, public-source adapters, company boards, cache, skill coverage, translate
  schemas/            Pydantic models
app/                  Browser UI (no build step)
docs/                 Job-search guide and upstream issue review
grammars/             JSON Schema + GBNF for llama.cpp
tests/                Unit, API, and optional browser checks
```

GitHub enrichment (`ats-match enrich`) is a stub: it exits 1. There is no GitHub API client.
