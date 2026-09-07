# Adapter Capability Matrix

> **Audit-only document.** No live traffic. Capability tags are
> read from the code, the ADRs, and the test fixtures. Each
> adapter row is followed by a column legend and an evidence note.

---

## Column legend

| Column | Meaning |
|---|---|
| **Code present** | A class file exists in `src/research_agent/sources/ats/` (or `official/`) |
| **Offline tests** | A test module in `tests/test_ats_adapters.py` (or dedicated file) exercises the adapter |
| **Historic evidence** | At least one real saved response exists in `tests/fixtures/` that the test consumes, OR a documented run report in `docs/reports/` describes a real historical execution |
| **Current live verified** | This audit does not perform live verification — **always `NOT_CHECKED_OFFLINE_AUDIT`** unless the project itself has a saved log/report timestamped after the last code change that proves a recent successful execution |
| **Request type** | GET / POST JSON / POST form / path interpolation / query interpolation / body interpolation / special headers |
| **Pagination** | offset / page number / cursor / single chunk / continuation token / load more |
| **Bootstrap/session** | preliminary HTML fetch / extract variable from HTML / CSRF token / cookies / session persistence |
| **Detail** | description inline / separate detail endpoint / apply enrichment / detail ID interpolation |
| **Full/filtered catalog** | whether the source returns all jobs in one call or requires filter params |
| **Completeness semantics** | explicit total / short final page / empty page / no-pagination all-items / catalog cap / filtered search / authoritative possible |
| **Potential SourceSpec fit** | could the adapter's wire be expressed by `source_spec/v0.1` without runtime changes? |

---

## Master matrix (12 rows)

| # | Adapter | File | Code present | Offline tests | Historic evidence | Current live verified | Request type | Pagination | Bootstrap / session | Detail | Full / filtered catalog | Completeness semantics | Potential SourceSpec fit |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | GreenhouseAdapter | `sources/ats/greenhouse.py` | yes | yes (`tests/test_ats_adapters.py::test_greenhouse_adapter_uses_public_board_api`) | yes (`tests/fixtures/greenhouse_jobs.json`, real captured response) | NOT_CHECKED_OFFLINE_AUDIT | GET, query, no body | **single chunk** (`GET /v1/boards/{token}/jobs?content=true` returns the whole board) | none | **inline** (`content` field in each job) | full (no filter required) | no-pagination all-items | **PASS_V01** in `runtime/candidates/cloudflare.json` (Cloudflare runs on Greenhouse). All extracted by `runtime/spec_executor.py` against the real fixture: see `runtime/test_candidates_batch3.py`. |
| 2 | LeverAdapter | `sources/ats/lever.py` | yes | yes (`test_lever_adapter_uses_public_postings_api`) | yes (`tests/fixtures/lever_jobs.json`) | NOT_CHECKED_OFFLINE_AUDIT | GET, query | **offset** (`?skip=N&limit=100`) | none | inline | full | explicit total (`offset + len(jobs) >= total` OR `len(jobs) < page_size`) | **SUPPORTED_V01**. `paging.strategy=offset`, `page_size=100`, `page_param=skip`. `body_path` not used (no body). |
| 3 | AshbyAdapter | `sources/ats/ashby.py` | yes | yes (`test_ashby_adapter_uses_public_posting_api_and_skips_unlisted`) | yes (`tests/fixtures/ashby_jobs.json`) | NOT_CHECKED_OFFLINE_AUDIT | GET, no query | **single chunk** (`GET /posting-api/job-board/{board}` returns whole board) | none | inline | full | no-pagination all-items | **SUPPORTED_V01**. Identical shape to Greenhouse; Cloudflare-style spec works. |
| 4 | SmartRecruitersAdapter | `sources/ats/smartrecruiters.py` | yes | yes (`test_smartrecruiters_adapter_uses_public_posting_api`) | yes (`tests/fixtures/smartrecruiters_jobs.json`) | NOT_CHECKED_OFFLINE_AUDIT | GET, query | **offset** (`?limit=100&offset=N`) | none | inline | full | explicit total (`totalFound` field) | **SUPPORTED_V01**. Identical to Mercedes/NVIDIA/Microsoft (Eightfold). |
| 5 | RadancyAdapter | `sources/ats/radancy.py` | yes | yes (`test_radancy_adapter_paginates_verified_server_rendered_contract`) | yes (`tests/fixtures/radancy_search_page_1.html` + `_page_2.html`) | NOT_CHECKED_OFFLINE_AUDIT | GET, HTML | **page number** (`?page=N`), 1-based, server-rendered HTML | none | inline HTML (no JSON API) | filtered (URL whitelist) | short final page + per-portal budget | **NEW_FROM_JOBRESEARCHCHEF (page_number)** — Radancy uses page=1, page=2, … which is the same shape as Apple (`page=1, 2, 307, 308`). Provides **second source of evidence** for the `page_number` pagination extension pressure already recorded for Apple. |
| 6 | SuccessFactorsRmkAdapter | `sources/ats/successfactors.py` | yes | yes (`test_successfactors_rmk_adapter_parses_and_follows_server_pagination`) | yes (`tests/fixtures/successfactors_search_page_1.html` + `_page_2.html`) | NOT_CHECKED_OFFLINE_AUDIT | GET, HTML | **page number + offset** (URL-based with `startrow` query param) | none | inline HTML (server-rendered) | full (via search URL) | short final page + per-portal budget | **NEW_FROM_JOBRESEARCHCHEF (startrow offset-like)** — SuccessFactors uses `startrow=0`, `startrow=25`, etc. This is functionally an offset but parameterized as a query field, not a `page` integer. Still fits `strategy=offset` with `page_param=startrow`. |
| 7 | WorkdayAdapter | `sources/ats/workday.py` | yes | yes (`test_workday_adapter_reads_bootstrap_and_posts_paginated_jobs`) | yes (`tests/fixtures/workday_landing.html` + `workday_jobs_page_1.json` + `workday_jobs_page_2.json`) | NOT_CHECKED_OFFLINE_AUDIT | **landing GET (HTML)**, then **POST JSON** to `/wday/cxs/{tenant}/{site}/jobs` | **offset** (in POST JSON body) | **BOOTSTRAP HTML → extract tenant+siteId via regex** | inline (jobs returned in POST response) | full | explicit total + per-portal budget + missing-page detection | **NEW_FROM_JOBRESEARCHCHEF (bootstrap)** — Workday's bootstrap pattern is exactly the `request.bootstrap` extension pressure recorded for Apple: preliminary HTML fetch, regex-extract two variables (tenant, siteId), use them in the next request. Provides **second source of evidence** for the bootstrap primitive. |
| 8 | PhenomAdapter | `sources/ats/phenom.py` | yes | yes (`test_phenom_adapter_parses_embedded_search_data_and_next_link`) | yes (`tests/fixtures/phenom_search_page_1.html` + `_page_2.html`) | NOT_CHECKED_OFFLINE_AUDIT | GET, HTML | **load-more (next link)**, embedded `phApp.ddo` JSON in HTML | none | inline (embedded JSON in HTML) | full (via search URL) | short final page + per-portal budget | **NEW_FROM_JOBRESEARCHCHEF (HTML-embedded JSON)** — Phenom pages contain `phApp.ddo = {...}; phApp.experimentData = {...}` scripts. Adapter parses with selectolax + regex. The v0.1 spec has no primitive for "extract JSON embedded in HTML"; would require a new field extraction mode. |
| 9 | OracleRecruitingCloudAdapter | `sources/ats/oracle.py` | yes | yes (`test_oracle_recruiting_cloud_follows_branded_link_and_paginates`) | yes (`tests/fixtures/oracle_landing.html` + `oracle_jobs_page_1.json` + `oracle_jobs_page_2.json`) | NOT_CHECKED_OFFLINE_AUDIT | **landing GET (HTML)**, then **GET JSON** to API | **page number** (`?start=0`, `?start=25`, ...) | **BOOTSTRAP HTML → follow branded link** | inline (jobs in API JSON) | full | explicit total + per-portal budget | **NEW_FROM_JOBRESEARCHCHEF (bootstrap + page_number)** — combines Workday-style bootstrap with Apple-style page_number. Provides **third source of evidence** for the `page_number` extension pressure (Apple, Radancy, Oracle). |
| 10 | AvatureAdapter | `sources/ats/avature.py` | yes | yes (`test_avature_adapter_parses_server_rendered_pages`) | yes (`tests/fixtures/avature_search_page_1.html` + `_page_2.html`) | NOT_CHECKED_OFFLINE_AUDIT | GET, HTML | **next URL (link)** in HTML | none | inline HTML | full | regex `_TOTAL` from HTML ("N results") | **NEW_FROM_JOBRESEARCHCHEF (next-URL pagination)** — Avature pages contain a "next" link. This is yet another pagination shape (cursor-like). Distinct from offset, page_number, and the inferred-cursor cases. |
| 11 | GoogleCareersAdapter | `sources/ats/google_careers.py` | yes | yes (`tests/test_google_careers_adapter.py`, 3 tests with MockTransport) | **NO fixture in `tests/fixtures/google_*`**. **NO historical log/report in `output/test_runs/*google*`** | NOT_CHECKED_OFFLINE_AUDIT | **POST form** (`application/x-www-form-urlencoded`) to `/_/HiringCportalFrontendUi/data/batchexecute` with `f.req=<JSON-of-arrays>` | **page number** 1-based (`args[0][7] = page`), page_size=20 | none observed (the legacy comment says "no browser, cookie, CSRF token, build id or referer is required by the observed endpoint" — but this is **claim, not evidence**) | inline (positional response, indices pinned in tests) | full | short final page + per-page-limit + observed total | **NEW_FROM_JOBRESEARCHCHEF (Boq/batchexecute RPC)** — Google Careers uses the same Comet/batchexecute pattern as Meta. Provides **second source of evidence** for the "GraphQL persisted query via Comet/Baq" entry already in `EXTENSION_PRESSURE_REGISTRY.md`. **NEVER** declares this adapter currently working — see `GOOGLE_ADAPTER_AUDIT.md` for the explicit audit. |
| 12 | GenericOfficialHtmlAdapter | `sources/official/generic.py` | yes | yes (`tests/test_generic_adapter.py`) | yes (`tests/fixtures/generic_job_page.html` + `avature_search_page_1.html` etc.) | NOT_CHECKED_OFFLINE_AUDIT | GET, HTML | **load more (anchor)** + JSON-LD `JobPosting` schema | none | inline (JSON-LD embedded) | filtered (robots.txt enforced) | short final page | **CUSTOM_LOGIC_ONLY**. The fallback adapter has heuristics for JSON-LD vs anchor-based job discovery. This is exactly what `runtime/source_spec/v0.1` rejects (universal inference). The generic adapter is the LAST-RESORT of the legacy runtime, not a candidate for the new architecture. |

---

## Cross-adapter capability matrix

This view abstracts the per-adapter row into a "which adapters
exercise which capability" matrix. **Use this to design v0.2
primitives** — capabilities exercised by ≥ 2 different adapter
families are strong candidates.

| Capability | Category | Adapters that exercise it |
|---|---|---|
| GET with query interpolation | request | Greenhouse, Lever, SmartRecruiters, Radancy (HTML), SuccessFactors (HTML), Oracle (HTML), Avature (HTML), Phenom (HTML), GenericOfficialHtml (HTML) |
| POST JSON body with offset in body | request | Workday |
| POST form-encoded body with JSON-of-arrays | request | GoogleCareers (positional Boq RPC) |
| POST form-encoded body with variables | request | (none — but Meta Careers uses the same Comet RPC pattern) |
| Bootstrap: HTML fetch + regex-extract 2 variables | bootstrap | Workday |
| Bootstrap: HTML fetch + follow branded link | bootstrap | Oracle |
| Bootstrap: CSRF token + cookie persistence | bootstrap | (Apple pattern, not in JobResearCHEF) |
| No bootstrap / no session | bootstrap | Greenhouse, Lever, Ashby, SmartRecruiters, Radancy (HTML), SuccessFactors (HTML), Phenom (HTML), Avature (HTML), GenericOfficialHtml |
| offset pagination in query | pagination | Lever, SmartRecruiters |
| offset pagination in body | pagination | Workday |
| page_number pagination in query | pagination | Radancy, SuccessFactors (via `startrow`) |
| page_number pagination in body | pagination | Oracle, GoogleCareers |
| single-chunk all-in-one response | pagination | Greenhouse, Ashby |
| load-more (next URL/anchor) | pagination | Phenom, Avature, GenericOfficialHtml |
| no pagination (single GET returns everything) | pagination | Greenhouse, Ashby |
| Dotted path extraction | extraction | (all JSON adapters) Greenhouse, Lever, Ashby, SmartRecruiters, Workday, Oracle |
| HTML parsing with selectolax | extraction | Radancy, SuccessFactors, Phenom, Avature, GenericOfficialHtml |
| HTML-embedded JSON in `<script>` blocks | extraction | Phenom |
| JSON-LD `JobPosting` schema detection | extraction | GenericOfficialHtml |
| Positional array indices in JSON | extraction | GoogleCareers (pinned in tests at lines 41-53) |
| HTML entity decoding | normalization | (implicitly, in `pipeline/normalizer.py::html_to_text`) |
| HTML strip (regex `<[^>]+>`) | normalization | `runtime/spec_executor.py::_strip_html` (legacy normalizer uses selectolax) |
| Multi-location join | normalization | SmartRecruiters, Greenhouse (offices[] / locations[]) |
| Date parsing from mixed formats | normalization | (legacy: `parse_datetime` accepts ISO, "May 28 2026", unix, etc.) |
| Inline description (full text in catalog item) | detail | All JSON APIs (Greenhouse, Lever, Ashby, SmartRecruiters, Workday, Oracle, GoogleCareers) |
| Separate detail endpoint | detail | (none — but legacy has `pipeline/detail_enrichment.py` for HTML-only sites) |
| robots.txt enforcement | detail | GenericOfficialHtml |
| Explicit total field | completeness | Workday, SmartRecruiters (totalFound), Oracle, GoogleCareers (`inner[2]`) |
| Short final page = end | completeness | All paginated adapters (Lever, SmartRecruiters, Workday, Oracle, Phenom, Avature) |
| Empty page = end | completeness | Greenhouse (no, doesn't have pagination), Ashby (no) |
| Catalog cap (filtered by page_size_max_jobs_per_portal) | completeness | All paginated adapters (500 or 5000) |
| Filtered search (URL requires search params) | completeness | Radancy, SuccessFactors, Oracle (search URL required), Phenom (search URL required) |
| Full catalog (no filter required) | completeness | Greenhouse, Lever, Ashby, SmartRecruiters, Workday, GoogleCareers |
| Authoritative OPEN/CLOSED possible | completeness | All adapters emit `is_complete_snapshot` boolean; downstream lifecycle uses it |

---

## v0.2 candidate capabilities (from this matrix)

Cross-adapter evidence count ≥ 2 source **different from the
existing registry entries**:

| New capability | Adapters exercising it | Evidence class | Notes |
|---|---|---|---|
| **HTML-embedded JSON** (`<script>window.X = {...}</script>` extraction) | Phenom, GenericOfficialHtml | HISTORIC_LEGACY_FIXTURE (2 sources) | v0.1 has no primitive; would need `extraction.description.embedded_json_in_html` or similar |
| **page_number pagination in query** | Radancy, SuccessFactors (as `startrow`), Oracle | HISTORIC_LEGACY_FIXTURE (3 sources) | Promotes `page_number` from 1 source (Apple, LIVE_FIXTURE) to **HIGH_CONFIDENCE_V02**. **Correction**: GoogleCareersAdapter is **NOT** evidence here because its positional page-index is different mechanism (positional array, not query string). |
| **Bootstrap → extract variables → use in next request** | Workday (tenant+siteId), Oracle (branded link) | HISTORIC_LEGACY_FIXTURE (2 sources) + Apple LIVE (CSRF token) | Promotes `bootstrap_request` from 1 source (Apple) to **HIGH_CONFIDENCE_V02**. |
| **load-more / next-link pagination** (cursor-like, opaque URL) | Phenom, Avature, GenericOfficialHtml | HISTORIC_LEGACY_FIXTURE (3 sources) | MEDIUM_CONFIDENCE_V02. New entry. |
| **POST form-encoded body** | GoogleCareersAdapter only | CODE_ONLY (1 source, MockTransport tests, no real fixture, stale `r06xKb` on 2026-09-05) | **Correction**: Apple does NOT use form-encoded (Apple uses JSON). Meta Careers uses form-encoded but its probe returned only an error envelope. So Apple and Meta are NOT evidence for this capability. |
| **filter search params required** (full catalog unavailable without search params) | Radancy, SuccessFactors, Oracle, Phenom | HISTORIC_LEGACY_FIXTURE (4 sources) | Existing evidence (`filtered_catalog` flag) covers this; v0.1 supports it via `source_of_truth: filtered_catalog` |

---

## SourceSpec `v0.1` already-covers vs needs-extension

| Capability | v0.1 supports? |
|---|---|
| GET + query interpolation | yes |
| POST JSON + body interpolation | yes |
| POST form-encoded body | **no** — GoogleCareers uses `application/x-www-form-urlencoded` with `f.req=<json>`. v0.1 has no `request.body_encoding: "form"` primitive |
| Single-chunk catalog (no pagination) | yes — `page_size=N, first=N` yields 1 offset |
| offset pagination in query/body | yes — `strategy=offset` |
| page_number pagination | **no** — registered in `EXTENSION_PRESSURE_REGISTRY.md` (Apple evidence + now 3 more from JobResearCHEF) |
| Load-more / next-link pagination | **no** — new entry; would need `strategy: "cursor_link"` or similar |
| Bootstrap request | **no** — registered (Apple); now 2 more from JobResearCHEF (Workday, Oracle) |
| HTML-embedded JSON extraction | **no** — new; would need `description.path` accepting dotted path that goes through HTML |
| HTML strip with selectolax | **partial** — v0.1 strip is regex-only; Cloudflare entity-encoded HTML survives |
| Robots.txt enforcement | **no** — but this is a transport concern, not a spec concern |
| Date parsing from mixed formats | **partial** — v0.1 has iso_date / iso_datetime / unix_seconds; Amazon's "May 28 2026" would not parse |
| Detail enrichment (separate second-stage fetch) | **partial** — v0.1 has `detail` block but no policy on when to fetch (no CYBER/NEEDS_MORE_DETAIL logic) |
| Catalog cap | **partial** — v0.1 has `max_requests_per_run` (per-run) but no `bulk_catalog_max_jobs_per_portal` (per-source) |

---

## Adapter-specific notes

### Greenhouse (the cleanest)

- Wire: `GET /v1/boards/{token}/jobs?content=true`
- No auth, no pagination, full board in one response
- `meta: {total: N}` is returned (per-source total, not totalFound)
- Detail: `content` field per job contains everything
- This is exactly the shape of `runtime/candidates/cloudflare.json` (PASS_V01)

### Workday (bootstrap exemplar)

- Step 1: `GET https://<tenant>.wd{N}.myworkdayjobs.com/en-US/<site>`
- Extract `tenant` from regex `tenant\s*:\s*['"]([^'"]+)['"]`
- Extract `siteId` from regex `siteId\s*:\s*['"]([^'"]+)['"]`
- Step 2: `POST https://<tenant>.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs` with JSON body `{"appliedFacets":{}, "limit":20, "offset":N, "searchText":""}`
- Returns `{total: N, jobPostings: [...]}`
- The bootstrap pattern is exactly what Apple needs but is not in v0.1

### Oracle (second bootstrap exemplar)

- Step 1: GET landing page (HTML)
- Find linked Candidate Experience page (or stay on landing if it has metadata)
- Extract `siteId`, `candidateSiteId`, etc. from embedded JSON
- Step 2: GET `https://.../api/jobSearch?start=0` etc., returns `{jobs:[...]}`
- Combines Bootstrap + page_number

### Google Careers (positional, fragile)

- Wire: `POST /about/careers/applications/_/HiringCportalFrontendUi/data/batchexecute`
- Form-encoded body: `f.req=[[["r06xKb","[args]",null,"generic"]]]`
- `args` is a 17-slot array; page is at index 7
- Response: positional arrays. Job is `[id, title, apply_url, responsibilities_html, qualifications_html, ..., description_html, ..., min_qualifications_html]`
- The adapter's `_JOB_ID = 0`, `_JOB_TITLE = 1`, etc. are hardcoded indices (pinned in tests at lines 41-53)
- The adapter comment at line 4: "The contract is positional and therefore deliberately pinned by tests."
- This is exactly the "Google Boq / possible opaque cursor" extension pressure recorded in `EXTENSION_PRESSURE_REGISTRY.md`
- See `GOOGLE_ADAPTER_AUDIT.md` for the explicit "this code exists but may not currently work" audit

### Phenom (HTML-embedded JSON)

- Step 1: GET landing HTML
- Extract `phApp.ddo = {...}; phApp.experimentData = ...` from inline script
- Extract base URL + search URL
- Step 2: GET search URL (HTML with embedded JSON)
- Parse JSON for jobs
- Step 3: parse "next" link for pagination
- Pattern: HTML-embedded JSON + load-more

### SmartRecruiters (offset)

- Wire: `GET /v1/companies/{company}/postings?limit=100&offset=N`
- Returns `{totalFound: N, content: [...]}`
- Same shape as NVIDIA/Microsoft (Eightfold) but different host
- Pattern: offset + explicit total
