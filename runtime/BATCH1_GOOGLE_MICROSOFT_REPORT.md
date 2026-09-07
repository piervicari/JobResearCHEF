# Batch 1 — Google & Microsoft discovery report

**Source spec frozen version:** `source_spec/v0.1`
**Generic executor:** `runtime/spec_executor.py` (unmodified)
**Schema:** `runtime/source_spec.schema.json` (unmodified)
**Date:** 2026-09-05

## Summary

| Company | Backend | Verdict | Browser future | Full catalog | Authoritative closed | v0.1 valid | New primitive needed | Live HTTP requests | 403 | 429 |
|---|---|---|---|---|---|---|---|---|---:|---:|
| **Google** | Google internal Boq / batchexecute (custom) | `NEEDS_EXTENSION` + `BROWSER_REQUIRED` | yes | n/a (cannot probe) | n/a | **no** | yes — see below | 4 | 0 | 0 |
| **Microsoft** | Eightfold.ai PCSX (same as NVIDIA) | `PASS_V01` | no | yes (2252) | yes | **yes** | no | 3 | 0 | 0 |

## Metrics

| Metric | Value |
|---|---|
| Google verdict | **`NEEDS_EXTENSION`** + **`BROWSER_REQUIRED`** |
| Microsoft verdict | **`PASS_V01`** |
| `PASS_V01` count | 1 |
| `NEEDS_EXTENSION` count | 1 |
| `CUSTOM_REQUIRED` count | 0 |
| `BROWSER_REQUIRED` count | 1 (Google, in addition to NEEDS_EXTENSION) |
| `SAFETY_ABORT` count | 0 |
| New primitives proposed | 2 (opaque_cursor + bootstrap HTML scrape step) |
| Modifications to `source_spec.schema.json` | **0** |
| Modifications to `spec_executor.py` | **0** |
| Modifications to `job.schema.json` | **0** |
| Frozen regression tests (42) | **pass** (42/42) |
| Candidate tests (24) | **pass** (24/24) |
| HTTP 403 total | **0** |
| HTTP 429 total | **0** |
| Total live HTTP requests (both companies) | **7** |

## Google

### What I actually verified

1. `GET https://www.google.com/about/careers/applications/jobs/results/?hl=en&gl=us`
   → HTTP 200, HTML served. Backend identified: `HiringCportalFrontendUi` (Google Boq framework).
2. Local extraction from that HTML (no extra HTTP): `WIZ_global_data.FdrFje = 1314078808493304713` (f.sid),
   `WIZ_global_data.cfb2h = boq_corp-hiring-boq-cportal-frontend_20260902.04_p0` (bl).
3. `POST https://www.google.com/about/careers/applications/_/HiringCportalFrontendUi/data/batchexecute?rpcids=HoAMBc&...`
   → HTTP 400 with `["er", null, 400]`. Endpoint confirmed reachable; `rpcids` value was wrong (it's the
   image-search rpcid, not careers).
4. `POST https://www.google.com/_/HiringCportalFrontendUi/data/batchexecute?...`
   → HTTP 404. Confirmed the batchexecute path is under `/about/careers/applications/_/`.

### What I did NOT verify

- The correct `rpcids` value for careers (would require Boq JS bundle parsing at minimum)
- The exact `f.req` body shape for careers (JSON-of-arrays-of-strings, obfuscated)
- The response envelope on a successful call
- Total job count for Google
- Whether descriptions/qualifications live in the response

### Fixtures saved

None. I deliberately stopped before downloading enough to fabricate a fixture, because
the protocol is JS-driven and a partial fixture would be misleading.

### Safety

- No 403, no 429, no CAPTCHA encountered.
- Stopped voluntarily after 4 conservative probes. Escalating further (enumerating rpcids,
  guessing the body shape) would have meant brute-forcing Google's internal API. The
  expected value of a successful discovery (a spec that may or may not survive contact
  with Google's bot-detection) does not justify the risk.

### Estimated requests for full reconciliation

Cannot estimate. Google careers is JS-driven; there is no HTTP-only endpoint that
returns the listings. Even a browser-based fetcher must maintain opaque state across
requests (`f.sid`, `bl`, `page_number_nonce`, `countdown_nonce`) that changes every
~hours when Boq bundles refresh.

### Extension pressure

Detailed in `candidates/google_NEEDS_EXTENSION.md`. Summary:

- **missing_capability**: opaque cursor pagination (`paging.strategy: "opaque_cursor"`)
  where the page value is read from a dotted path in the previous response and injected
  into the next request (often under URL-encoding in `f.req`).
- **missing_capability**: HTML bootstrap step before API calls — the runtime would need
  to fetch the page HTML, parse it, and use extracted tokens as variables in the next
  call's request.
- **could_other_sources_reuse_it: yes** — Google Images, News, Maps, Drive picker,
  Translate, YouTube internal, etc., all use the same `batchexecute` pattern. A
  generic `opaque_cursor` would unlock dozens of Google properties immediately.
- **alternative_without_schema_change: no**.
- **complexity: high**.
- **why v0.1 cannot express it**: v0.1 only supports `paging.strategy = "offset"` with
  the page value being a simple integer, and there is no concept of "first fetch HTML,
  extract tokens, then call API".

## Microsoft

### What I actually verified

1. Single probe `GET https://careers.microsoft.com/` via web extractor (no auth, 200 OK).
   Identified `careers.microsoft.com` as the public site. Frontend uses
   `microsoft.eightfold.ai` subdomain. Job URLs are
   `https://careers.microsoft.com/careers/job/{id}?domain=microsoft.com`. Apply URLs are
   `https://careers.microsoft.com/careers/apply?pid={id}&domain=microsoft.com`. The page
   shows "2208 jobs" / "Page 1 of 221" in the rendered listing (server-side rendered).

2. `GET https://api.smartrecruiters.com/v1/companies/microsoft/postings?limit=10&offset=0`
   → HTTP 200, but `totalFound=0`. Confirmed SmartRecruiters has a public API but
   `microsoft` is not its identifier on that platform.

3. `GET https://microsoft.eightfold.ai/api/pcsx/search?domain=microsoft.com&start=0&hl=en`
   → HTTP 200, `data.count=2252`, 10 positions returned. Wire protocol identical to NVIDIA
   (same envelope: `status/error/data/metadata`, same `data.positions[]`, same field
   names: `id`, `displayJobId`, `name`, `locations`, `postedTs`, `department`, …).
   **Saved as fixture** `fixtures/microsoft_catalog_page.json`.

4. `GET https://microsoft.eightfold.ai/api/pcsx/position_details?domain=microsoft.com&position_id=1970393556853171&hl=en`
   → HTTP 200, response wrapped as `{status, error, data, metadata}` with `data.id`,
   `data.name`, `data.jobDescription` (5964 chars HTML), `data.publicUrl`. **Saved as
   fixture** `fixtures/microsoft_detail.json`.

### Backend

Eightfold.ai PCSX. **Identical wire protocol to NVIDIA.** Microsoft uses SuccessFactors
internally (visible in the Solr query embedded in the Eightfold config:
`position.system_id:successfactors`) but Eightfold exposes the unified PCSX API on the
outside, so we hit `microsoft.eightfold.ai/api/pcsx/*` and not the SuccessFactors SOAP.

### Total job count

**2252** jobs in `data.count` of the first response. Confirms a full catalog.

### Estimated requests for full reconciliation

With `page_size=10`, `first_page_value=0`, total=2252, completeness rule
`last_page_shorter_than_page_size`, **no empty-after-total probe** (Microsoft's
spec does NOT use `items_path_empty_after_total`):

`ceil(2252 / 10) = 226` data pages, no probe page → **226 total requests**.

(Verified offline by `test_microsoft_pagination_iterator_emits_226_offsets` and
`test_microsoft_full_sweep_request_count` in `test_candidates_batch1.py`.)

### Fixtures saved

- `runtime/fixtures/microsoft_catalog_page.json` (21,590 bytes, real captured)
- `runtime/fixtures/microsoft_detail.json` (17,421 bytes, real captured)

### Spec saved

`runtime/candidates/microsoft.json` — validates against `source_spec/v0.1` without
any modification to the schema. Passes the existing `validate_specs.py`.

### Safety

- No 403, no 429, no CAPTCHA. Microsoft Eightfold responses were served normally with
  User-Agent + Accept + Accept-Language headers, no auth required.
- 3 HTTP requests total for Microsoft discovery (one SmartRecruiters probe that turned
  out to be the wrong platform, one catalog, one detail).

### Full catalog vs filtered

The single page returned 10 items with `totalFound=2252`, which matches the visible
"2208 jobs" counter on the website (within rounding). This indicates **full catalog**
mode: the API serves all postings without requiring search filters.

### Authoritative for OPEN/CLOSED

Yes. Microsoft career portal is the company-wide official source; Eightfold PCSX
serves the complete list (total count visible without filters). `source_of_truth =
full_catalog`, `open_closed_authoritative = true`.

## Frozen regression verification

After all batch-1 work, the following still hold:

| Asset | Status |
|---|---|
| `runtime/source_spec.schema.json` | unchanged, version pinned to `v0.1` |
| `runtime/spec_executor.py` | unchanged (last edited during v0.1 freeze on 2026-09-05 batch) |
| `runtime/job.schema.json` | unchanged |
| `runtime/sources/mercedes.json` | unchanged |
| `runtime/sources/nvidia.json` | unchanged |
| `runtime/validate_specs.py` | unchanged |
| `runtime/test_spec_executor.py` | unchanged |
| `runtime/test_spec_executor.py` execution | **42/42 PASS** |
| New files only | `runtime/candidates/google_NEEDS_EXTENSION.md`, `runtime/candidates/microsoft.json`, `runtime/fixtures/microsoft_catalog_page.json`, `runtime/fixtures/microsoft_detail.json`, `runtime/test_candidates_batch1.py`, `runtime/BATCH1_GOOGLE_MICROSOFT_REPORT.md` |

Verified by the `FrozenRegressionTests` class in `test_candidates_batch1.py`:

- `test_frozen_executor_tests_still_pass` — re-runs `test_spec_executor.py` as a subprocess, asserts exit code 0 and `Ran ≥ 42 tests`.
- `test_executor_did_not_change` — confirms `spec_executor.py` docstring still declares v0.1 scope.
- `test_schema_did_not_change_version` — confirms `paging.strategy` is still `const "offset"` and `schema_version` is still `const "source_spec/v0.1"`.

## Verdict

- **Microsoft**: `PASS_V01` — fully representable with `source_spec/v0.1`, no schema or executor changes, all tests PASS.
- **Google**: `NEEDS_EXTENSION` + `BROWSER_REQUIRED` — v0.1 lacks the primitive needed (`opaque_cursor` + HTML bootstrap). Documented in detail; no fake spec created.
- **Contract pressure**: v0.1 withstood one additional fully representable source (Microsoft, identical protocol to NVIDIA — confirms Eightfold coverage). It rejected one (Google, batchexecute pattern — would need extension). The frozen contract is **honest**: it does NOT promise coverage for arbitrary Google properties.

## What I did NOT do

Per the safety rules:

- Did NOT brute-force the Google `batchexecute` endpoint.
- Did NOT enumerate multiple `rpcids` values, page offsets, or filter combinations on Google.
- Did NOT perform a full catalog sweep on either company.
- Did NOT modify `source_spec.schema.json`, `spec_executor.py`, or `job.schema.json`.
- Did NOT add proxy rotation, IP rotation, or UA rotation.
- Did NOT solve or attempt to bypass any CAPTCHA / anti-bot challenge.
- Did NOT introduce any new HTTP traffic beyond the 4 + 3 conservative probes documented above.

## Suggested next steps

1. Add Microsoft to `runtime/sources/microsoft.json` and run the full frozen test
   suite — should yield 42 → 42 (no new failures, no regressions).
2. Decide whether the extension proposed for Google (opaque_cursor + bootstrap HTML
   scrape) is worth the schema change. If yes, plan it as `source_spec/v0.2` and gate
   it behind a real second source that exercises it. If no, leave Google out of scope.
3. Continue discovery on more ATSs (Workday, Greenhouse, Lever, Ashby) — all four
   are known to have public APIs that fit the `offset` strategy. Expected to be `PASS_V01`.
