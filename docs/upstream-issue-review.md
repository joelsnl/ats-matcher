# Upstream issues: what we addressed

Reviewed on 2026-09-12 using the public GitHub issues API, including open and closed
issues and their comments. Nine issues were present, excluding pull requests; two were
open. This records changes in **our ATS Matcher implementation**. It does not change
or close anything in the upstream repository.

| Upstream issue | What it means for this tool | Action and coverage |
| --- | --- | --- |
| [#13: Multiple filters and custom days](https://github.com/VishwaGauravIn/linkedin-jobs-api/issues/13) - open | People want to find, for example, both part-time and internship roles, or both remote and hybrid roles. | Added multiple job types, work arrangements, and experience levels across the browser, local API, and CLI. Added a custom 1–365 day window. Existing single-value inputs still work. Tests check combinations, invalid choices, dates, cache separation, and API/CLI requests. |
| [#16: Axios dependency report](https://github.com/VishwaGauravIn/linkedin-jobs-api/issues/16) - open | The report concerns the JavaScript package's request library. | Not applicable to our dependency tree: our adapter uses Python's standard library and imports no Axios or upstream npm package. Added request-error tests for rate limits, redirects, access blocks, server failures, and other HTTP errors. The issue's version claims are not treated as verified dependency advice. |
| [#9: Higher limits return smaller cached results](https://github.com/VishwaGauravIn/linkedin-jobs-api/issues/9) - closed | A second, larger search must not reuse the smaller result set. | Already avoided by including the full query, limit, and page in our cache key. Added a regression that searches for one then three jobs and verifies the larger response, plus isolation for multiple filters and custom days. Our per-search maximum remains 100. |
| [#8: 24-hour searches return older jobs](https://github.com/VishwaGauravIn/linkedin-jobs-api/issues/8) - closed | The reported payload uses `24h`, while the documented option is `24hr`. | Accept both spellings and explicitly send the 86,400-second source filter. Added a test using the reported payload. Unknown dates are rejected instead of silently disabling the filter. LinkedIn can still ignore filters or show reposted jobs; these tests verify our request, not the source's date accuracy. |
| [#7: Missing pagination](https://github.com/VishwaGauravIn/linkedin-jobs-api/issues/7) - closed | Users need to continue through search results. | Already supported with zero-based pages, 25-position source offsets, and a Next source page button. Regression coverage checks offsets, duplicate pages, retained filters, and partial failures. A limit that cuts a source page still advances to the next source page; unused items in that batch are not carried over. |
| [#5: Company logos](https://github.com/VishwaGauravIn/linkedin-jobs-api/issues/5) - closed | Logos may be in `src` or a delayed-image attribute. | Both are supported. Added tests for each, placeholder images, and malformed URLs. An unusable optional logo no longer discards a valid job. The browser currently uses company initials; logo URLs are available in API/CLI results. |
| [#6: Module import error](https://github.com/VishwaGauravIn/linkedin-jobs-api/issues/6) - closed | Older Node versions cannot parse the upstream JavaScript syntax. | Not applicable to the Python adapter. Our documented runtime is Python 3.11+. No Node server or npm dependency is required to search. |
| [#3: Runtime error and later 429 report](https://github.com/VishwaGauravIn/linkedin-jobs-api/issues/3) - closed | The initial error is old Node syntax; a later comment reports LinkedIn limiting requests. | Node syntax does not apply. Added a shared rate-limit pause that respects `Retry-After`, including HTTP-date values, with a 60-second fallback. Tests verify no immediate re-request across different queries, recovery after the pause, cached access, and preservation of earlier results when a later page fails. LinkedIn can still block or limit access. |
| [#14: Company size](https://github.com/VishwaGauravIn/linkedin-jobs-api/issues/14) - closed | Users want jobs only from companies above a certain headcount. | The maintainer says this search has no company-size filter, and our source cards provide no headcount. We do not present a filter we cannot honor. Adding it needs a separate company-data source with known coverage. |

## Try the new controls

In **Live job search**, tick more than one work arrangement. Open **More search options**
to select several job types or experience levels. Under **Posted within**, choose
**Choose number of days** and enter, for example, 3. Leave all checkboxes in a group
unticked to include every option in that group.

```powershell
ats-match search --keyword "engineer" --job-type "part_time,internship" --workplace "remote,hybrid" --experience "entry_level,associate" --days 3
```

## Verification

- 111 non-model tests passed, including 36 added regression cases. The existing model
  evaluation was excluded; no CV-model behavior changed.
- Browser checks use controlled job responses to test multiple selections, custom days,
  state retention, pagination, clearing filters, mobile layout, rate-limit messages,
  and safe rendering of source content.
- The new filter combinations have not been verified against live LinkedIn results.
  Source availability and filtering behavior remain outside this adapter's control.
- Pauses and caches are local to a running provider instance. Restarting the tool or
  launching another process does not share that state.
