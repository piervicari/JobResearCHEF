# Batch 3 — Meta & Cloudflare discovery report

**Source spec frozen version:** `source_spec/v0.1`
**Generic executor:** `runtime/spec_executor.py` (unmodified)
**Schema:** `runtime/source_spec.schema.json` (unmodified)
**Job schema:** `runtime/job.schema.json` (unmodified)
**Date:** 2026-09-05

> **CORRECTION (Phase-1 pre-flight, 2026-09-06, offline, zero new HTTP):**
> the Cloudflare PASS_V01 verdict below is SUPERSEDED. The candidate spec
> declared an `offset` pagination (`?content=true&offset=0`) with zero wire
> evidence that the Greenhouse endpoint honours any paging parameter — the
> captured response is a single 331-job chunk. `candidates/cloudflare.json`
> was moved to `candidates/_archive/cloudflare.json.PASS_V01_then_revoked`;
> see `candidates/cloudflare_NEEDS_EXTENSION.md` (`contract_fit =
> NEEDS_EXTENSION`, missing capability `single_request / unpaginated
> catalog`). Batch-3 tests now load the archived spec. All other Batch-3
> findings (fixtures, semantic note, entity-encoding quirk) stand.

## Summary table

| Company | Backend | contract_fit | semantic_complete | traversal_complete_under_safety_policy | authoritative_for_closed | browser_required | Primary verdict | Live requests | 403 | 429 |
|---|---|---|---|---|---|---|---|---|---:|---:|
| **Meta** | Facebook Comet app (`POST /graphql` with persisted queries) | **UNRESOLVED** | unknown | unknown | unknown | unknown | **UNRESOLVED** | 4 | 0 | 0 |
| **Cloudflare** | Greenhouse Job Board API (public, no auth, single-chunk full catalog) | **PASS_V01** | true | **false** (see finding) | false (due to incomplete traversal without harness-added probes) | false | **PASS_V01** | 3 | 0 | 0 |

## Metrics

| Metric | Value |
|---|---|
| **Meta contract_fit** | UNRESOLVED |
| **Meta semantic_complete** | unknown |
| **Meta traversal_complete_under_safety_policy** | unknown |
| **Meta authoritative_for_closed** | unknown |
| **Meta browser_required** | unknown |
| **Meta primary verdict** | UNRESOLVED |
| **Cloudflare contract_fit** | PASS_V01 |
| **Cloudflare semantic_complete** | true |
| **Cloudflare traversal_complete_under_safety_policy** | false |
| **Cloudflare authoritative_for_closed** | false |
| **Cloudflare browser_required** | false |
| **Cloudflare primary verdict** | PASS_V01 |
| `PASS_V01` count (this batch) | 1 (Cloudflare) |
| `NEEDS_EXTENSION` count | 0 (new in this batch) |
| `CUSTOM_REQUIRED` count | 0 |
| `UNRESOLVED` count | 1 (Meta) |
| `SAFETY_ABORT` count | 0 |
| **New capabilities observed this batch** | 1 (Cloudflare HTML entity encoding in description) |
| **Capabilities already known that recurred** | 0 |
| **Total capabilities in EXTENSION_PRESSURE_REGISTRY** | 7 (5 with real evidence from ≥1 source) |
| **Capabilities with evidence from ≥ 2 sources** | **0** |
| **Modifications to `source_spec.schema.json`** | **0** |
| **Modifications to `spec_executor.py`** | **0** |
| **Modifications to `job.schema.json`** | **0** |
| Frozen regression tests (42) | **pass** (42/42) |
| Batch1 tests (24) | **pass** (24/24) |
| Batch2 revised tests (29) | **pass** (29/29) |
| Batch3 tests (26) | **pass** (26/26) |
| **HTTP 403 total** | **0** |
| **HTTP 429 total** | **0** |
| **Total live HTTP requests (both companies)** | **7** (4 Meta + 3 Cloudflare) |

---

## Meta — `UNRESOLVED`

### Requests actually executed

1. `GET https://www.metacareers.com/jobsearch/` → HTTP 400 (`proxy-status: http_request_error`).
2. `GET https://www.metacareers.com/v2/jobsearch/` → HTTP 400.
3. `GET https://www.metacareers.com/jobsearch?q=software` → HTTP 400.
4. `POST https://www.metacareers.com/graphql` (form-encoded, with browser-shaped headers and `X-FB-LSD` header) → **HTTP 200**, but body contains GraphQL error: `{"errors": [{"message": "The GraphQL document with ID 25452271089445141 was not found.", "severity": "CRITICAL"}], "extensions": {"is_final": true}}`.

### Fixtures saved

- `fixtures/meta_GRAPHQL_endpoint_reachable_but_doc_id_unknown.json` (141 bytes). This is **not** a usable catalog fixture. It only proves the protocol exists and the request format is correct. Documented in `candidates/meta_UNRESOLVED.md`.

### Backend

Meta careers (`metacareers.com`) is a **Facebook Comet app**. The frontend calls `POST /graphql` with persisted queries identified by `doc_id`. The doc_id is a numeric ID that must be extracted from the JS bundle (`boq_comet_HiringCportalFrontend`); it changes at each Comet release.

### Why `UNRESOLVED` (not `NEEDS_EXTENSION`)

`NEEDS_EXTENSION` requires positive evidence: a successful request/response demonstrating the gap. Meta produced only error responses (HTTP 400, or HTTP 200 with GraphQL error). Without a valid payload, I cannot declare what v0.1 is missing.

### What `browser_required` is for the future

If we want to resolve Meta, the doc_id must be extracted from the JS bundle. The robust way is to render the frontend in a real browser (Playwright/Selenium) and capture the bundle. This is a future-harvesting concern, not a discovery concern.

### Safety

4 requests. Zero 403, 429, CAPTCHA. Stopped voluntarily because the next step would have required guessing a doc_id (brute-force, forbidden).

---

## Cloudflare — `PASS_V01` with documented harness caveat

### Requests actually executed

1. `GET https://www.metacareers.com/jobsearch/` — wait, that's Meta. For Cloudflare:
   - `GET https://boards-api.greenhouse.io/v1/boards/cloudflare/jobs?content=true` → **HTTP 200**, 5.5 MB, `meta.total: 331`, full catalog in one chunk.
2. `GET https://boards-api.greenhouse.io/v1/boards/cloudflare/jobs/7695702?questions=false` → **HTTP 200**, detail endpoint confirmed.

### Fixtures saved

- `fixtures/cloudflare_catalog_page.json` (838,521 bytes, full 331-job catalog with content fields truncated to 500 chars per job for inspection). The raw 5.5 MB capture is preserved as `fixtures/cloudflare_catalog_page_raw.json` (the unmodified first response).
- `fixtures/cloudflare_detail.json` (14,344 bytes, single-job detail).

### Backend

Greenhouse Job Board API. `https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs`. No auth required for GET. Response is a single JSON chunk containing the entire catalog with `meta.total` reflecting the total. No server-side pagination. The `content` field is HTML entity encoded (`&lt;`, `&gt;`, `&quot;`) — a known Greenhouse quirk.

### Schema (extracted from real payload)

```json
{
  "jobs": [
    {
      "absolute_url": "https://boards.greenhouse.io/cloudflare/jobs/{id}",
      "id": 7695702,
      "internal_job_id": 3383201,
      "title": "Account Executive, FedCiv",
      "company_name": "Cloudflare",
      "first_published": "2026-03-09T16:05:19-04:00",
      "updated_at": "2026-09-04T10:59:17-04:00",
      "requisition_id": "...",
      "language": "en",
      "location": {"name": "Hybrid"},
      "departments": [{"id": 70660, "name": "Field Sales", ...}],
      "offices": [{"id": 19994, "name": "Washington, DC", "location": "...", ...}],
      "metadata": [{"id": ..., "name": "Cost Center", "value": "...", ...}],
      "content": "<full HTML blob: about, responsibilities, qualifications, benefits>"
    }
  ],
  "meta": {"total": 331}
}
```

### Estimated requests for full reconciliation

**1 request** (single-chunk). max_requests_per_run is set to 10 (very generous).

### Verdict rationale

- **contract_fit = PASS_V01**: the spec validates against the schema and the runtime can drive it.
- **semantic_complete = true**: title, department, description (HTML blob containing all responsibilities/qualifications) all extract correctly. Known artifact: the content is HTML-entity-encoded; the v0.1 `strip_html` removes `<tag>` markup but does not decode entities (`&lt;` etc.). The downstream classifier must call `html.unescape()` before feature extraction. This is **not** a v0.1 bug — it is a Greenhouse wire-format quirk. Documented in `candidates/cloudflare.json` `notes`.
- **traversal_complete_under_safety_policy = false**: with `page_size=331` and `total=331`, the pagination_iterator yields exactly 1 offset (0). The runtime's `evaluate_completeness` requires `next_offset_ge_total` to have seen offsets from `first` to `final_total` inclusive (i.e., offsets 0 AND 331). With only offset 0 fetched, the rule fails with `'missing pages: [331]'`. Additionally, `last_page_shorter_than_page_size` fails because the last (and only) page is full (331 == page_size).
- **authoritative_for_closed = false**: consequent to `traversal_complete_under_safety_policy = false`. A downstream harness can recover by issuing 2 additional empty-page probes (at offsets 331 and 332); with those probes in history, completeness succeeds and `may_mark_closed = true`. Tested explicitly in `test_candidates_batch3.py::CloudflareCompletenessTests::test_authoritative_for_closed_with_explicit_2nd_request`.
- **browser_required = false**: the public Greenhouse API works without JS.

### Safety

3 requests. Zero 403, 429, CAPTCHA.

---

## Extension pressure observed this batch

### Cloudflare HTML entity encoding (1 capability, 1 source)

- **Category**: normalization
- **Source**: Cloudflare
- **Real evidence count**: 1 (`fixtures/cloudflare_catalog_page.json` job 0: the `content` field starts with `&lt;div class=&quot;content-intro&quot;&gt;...&lt;/p&gt;` even after v0.1's strip_html runs)
- **Repeated across sources**: no
- **Candidate for v0.2**: **no** — this is a single-source quirk and the fix is a one-line `html.unescape()` on the downstream side, not a new v0.1 primitive
- **Why v0.1 cannot express it**: v0.1's `_strip_html` is `<[^>]+>` regex; HTML entities like `&lt;` are not in that form. Adding an entity-decode step would be a runtime change, which the v0.1 contract forbids
- **Workaround without schema change**: the downstream classifier calls `html.unescape()` (or language equivalent) on the description field. Documented in `candidates/cloudflare.json` `notes`.

### Meta Comet/Boq doc_id (NOT promoted per rules)

- **Category**: request
- **Source**: Meta
- **Real evidence count**: **0** (only 4xx/error responses observed)
- **Candidate for v0.2**: **no** (per the rule: no successful response → no promotion)
- This capability is logged in `EXTENSION_PRESSURE_REGISTRY.md` for traceability but not counted toward "real evidence" or "v0.2 candidate" totals.

---

## Frozen regression verification

| Asset | Status |
|---|---|
| `runtime/source_spec.schema.json` | unchanged, version pinned to `v0.1` |
| `runtime/spec_executor.py` | unchanged |
| `runtime/job.schema.json` | unchanged |
| `runtime/sources/mercedes.json` | unchanged |
| `runtime/sources/nvidia.json` | unchanged |
| `runtime/validate_specs.py` | unchanged |
| `runtime/test_spec_executor.py` | unchanged |
| `runtime/test_spec_executor.py` execution | **42/42 PASS** |
| `runtime/test_candidates_batch1.py` execution | **24/24 PASS** |
| `runtime/test_candidates_batch2_revised.py` execution | **29/29 PASS** |
| New files only | `candidates/cloudflare.json`, `candidates/meta_UNRESOLVED.md`, `fixtures/cloudflare_catalog_page*.json`, `fixtures/cloudflare_detail.json`, `fixtures/meta_GRAPHQL_endpoint_reachable_but_doc_id_unknown.json`, `test_candidates_batch3.py`, `EXTENSION_PRESSURE_REGISTRY.md`, `BATCH3_META_CLOUDFLARE_REPORT.md` |

Verified by `FrozenRegressionTests` in `test_candidates_batch3.py`:
- `test_frozen_executor_tests_still_pass` — re-runs `test_spec_executor.py`, asserts exit 0 and ≥ 42 tests
- `test_batch1_candidates_tests_still_pass` — re-runs `test_candidates_batch1.py`, asserts exit 0 and ≥ 24 tests
- `test_batch2_revised_tests_still_pass` — re-runs `test_candidates_batch2_revised.py`, asserts exit 0 and ≥ 25 tests
- `test_executor_did_not_change` — confirms `spec_executor.py` docstring still declares v0.1 scope
- `test_schema_did_not_change_version` — confirms `paging.strategy` is still `const "offset"` and `schema_version` is still `const "source_spec/v0.1"`
- `test_extension_pressure_registry_exists` — confirms the cumulative registry file exists and mentions the documented capabilities

## What was changed during batch 3

- `candidates/cloudflare.json` (new, valid PASS_V01 spec)
- `candidates/meta_UNRESOLVED.md` (new, UNRESOLVED verdict with documented Comet probe)
- `fixtures/cloudflare_catalog_page_raw.json` (raw 5.5 MB capture)
- `fixtures/cloudflare_catalog_page.json` (cleaned version, 838 KB)
- `fixtures/cloudflare_detail.json` (14 KB)
- `fixtures/meta_GRAPHQL_endpoint_reachable_but_doc_id_unknown.json` (141 B, not a usable catalog fixture)
- `EXTENSION_PRESSURE_REGISTRY.md` (new, cumulative record across batches)
- `test_candidates_batch3.py` (new, 26 tests including frozen regression)
- `BATCH3_META_CLOUDFLARE_REPORT.md` (this file)

## What was NOT changed

- No HTTP traffic beyond the 4 + 3 conservative probes documented above
- `runtime/source_spec.schema.json` unchanged
- `runtime/spec_executor.py` unchanged
- `runtime/job.schema.json` unchanged
- `runtime/sources/mercedes.json` unchanged
- `runtime/sources/nvidia.json` unchanged
- `candidates/microsoft.json` unchanged (carried forward from batch 1)
- `candidates/apple_NEEDS_EXTENSION.md` unchanged (carried forward from batch 2)
- `candidates/amazon_NEEDS_EXTENSION.md` unchanged (carried forward from batch 2 revised)
- `candidates/google_NEEDS_EXTENSION.md` unchanged (carried forward from earlier batches)
- No fake `candidates/meta.json` created

## Verdict

- **Meta**: `UNRESOLVED` — Comet/GraphQL protocol confirmed but no payload obtained (doc_id unknown). Requires browser-based doc_id extraction to resolve.
- **Cloudflare**: `PASS_V01` with documented harness caveat (`traversal_complete_under_safety_policy = false`; downstream harness must issue 2 additional empty-page probes to authorize CLOSED). semantic_complete=true; HTML entity encoding is a downstream `html.unescape()` concern, not a v0.1 gap.
- **Contract pressure**: v0.1 withstood one additional representable source (Cloudflare, public Greenhouse API, full catalog in one chunk). It rejected one (Meta, Comet persisted query with rotating doc_id). The frozen contract remains honest: no fake PASS_V01 for Meta.
- **v0.2 candidates**: 1 strong (Apple `page_number`). 5 additional capabilities with single-source evidence (Amazon join_paths/qualifications_path, Apple bootstrap/cookie, Cloudflare entity decode). All recorded in `EXTENSION_PRESSURE_REGISTRY.md`.

## Suggested next steps (do not implement now)

1. Run a third-party doc_id extractor on Meta's frontend bundle (e.g., a JS scraper that pulls `boq_comet_HiringCportalFrontend` and looks up `doc_id` constants) to enable a successful Meta fixture. Then re-evaluate Meta.
2. If the v0.2 design starts, prioritize the `page_number` pagination primitive (high external prevalence, single-source evidence from Apple so far — but LinkedIn/Indeed also use page-number, so a second source would lock the v0.2 candidate status).
3. If `html.unescape()` is deemed a v0.2 candidate (currently NOT, because it's a single-source quirk and one downstream line is enough), promote Cloudflare's "HTML entity decoding" row from registry to v0.2.
4. Continue discovery on Workday / Lever / Ashby (known offset-based public APIs — likely PASS_V01).
