# Google Adapter Audit (specific deep dive)

> **Audit-only document.** Pure reading. No HTTP traffic. No
> browser. No modification. The goal is to honestly document what
> the legacy `GoogleCareersAdapter` actually does, what is
> tested, what evidence exists, and **what we cannot claim**.

The principle: never say "Google works" without positive evidence.
When only code exists, we mark `CODE_PRESENT` and document the
gap.

---

## A. Inventory of Google-related artifacts in JobResearCHEF

Files that mention Google or careers-related BOQ/Comet code:

| File | Size | Purpose |
|---|---:|---|
| `src/research_agent/sources/ats/google_careers.py` | 287 LOC | The adapter implementation |
| `tests/test_google_careers_adapter.py` | 122 LOC | 3 offline tests using `httpx.MockTransport` |
| `docs/decisions/0049-google-careers-anonymous-structured-rpc-adapter.md` | ~50 LOC | ADR dated 2026-09-02 accepting the adapter |
| `docs/decisions/0050-google-full-catalog-budget-is-probe-scoped-not-global.md` | ~50 LOC | ADR accepting the probe-scoped network budget |
| `scripts/run_google_careers_probe.sh` | 197 LOC | Operator script for live probe |
| `docs/CANARY_RESULTS_2026-09-02.md` | n/a | Canary results document (NOT specific to Google) |
| `docs/reports/` | n/a | **No `*google*` file in this directory** |

Other Google mentions:
- `output/test_runs/*.log` mention `google/gemini-...` model names (LLM provider, not Google Careers)
- `data/raw/` does not contain Google fixtures
- `tests/fixtures/` does NOT contain a Google fixture

---

## B. Adapter implementation: `src/research_agent/sources/ats/google_careers.py`

### B.1 Request construction

```python
_RPC_URL = (
    "https://www.google.com/about/careers/applications/_/"
    "HiringCportalFrontendUi/data/batchexecute"
)
_SEARCH_RPC = "r06xKb"          # hardcoded persisted-query ID
_PAGE_SIZE = 20                # Google-fixed
_ARG_SLOTS = 17                # positional args array length
_ARG_QUERY = 0
_ARG_LOCALE = 4
_ARG_PAGE = 7                  # page number is at index 7
```

The adapter sends a `POST` with `Content-Type: application/x-www-form-urlencoded;charset=UTF-8`
and form body `{"f.req": <JSON>}` where the JSON is the positional
args array. **No browser, no cookie, no CSRF token, no build id, no
referer** — per the comment in line 4.

### B.2 RPC positional indices

```python
_JOB_ID = 0
_JOB_TITLE = 1
_JOB_APPLY_URL = 2
_JOB_RESPONSIBILITIES = 3
_JOB_QUALIFICATIONS = 4
_JOB_COMPANY = 7
_JOB_LOCATIONS = 9
_JOB_DESCRIPTION = 10
_JOB_CREATED_TS = 12
_JOB_UPDATED_TS = 13
_JOB_MIN_QUALIFICATIONS = 19
```

The adapter comment at line 41: "Google job-record slots. These
are not documented field names; pin them in tests."

### B.3 Pagination

The adapter uses `page = 1, 2, 3, ...` (1-based integer, step=1,
page_size=20). Up to `context.page_limit(10_000)` pages. The
adapter's own termination conditions:
- empty page → only safe after `len(collected) >= total`
- last partial page → `len(jobs) < self._PAGE_SIZE`
- `len(collected) >= total`

The legacy is therefore **page-number-based**, identical to Apple.

### B.4 Extraction

- Locations: `[entry[0]]` for name, `[entry[2]]` for city, `[entry[5]]` for country, where `entry` is itself an array of length ≥ 6.
- Description: composed of multiple HTML sections joined by `<h2>` headings. Sections: Description, Responsibilities, Qualifications, Minimum qualifications. Duplicates dropped.
- Timestamps: `[value[0]]` if value is a list starting with int/float (unix seconds).

### B.5 Code summary

The adapter is a single-class, fully-implemented, well-commented
positional parser for Google's anonymous Boq RPC. It is **production-grade code**.

---

## C. Offline tests: `tests/test_google_careers_adapter.py`

```python
def test_google_careers_adapter_pages_structured_rpc_and_returns_complete_catalog() -> None:
    ...
    assert seen_pages == [1, 2]
    assert result.is_complete_snapshot is True
    assert len(result.jobs) == 21

def test_google_careers_adapter_marks_page_limited_scan_incomplete() -> None: ...

def test_google_careers_adapter_requires_platform_signature_not_company_id() -> None: ...
```

The tests use `httpx.MockTransport` with hand-constructed mock
responses. **No real saved Google response is used.** The fixture
is synthesized in-test via `_rpc_response(jobs, total)`.

The mock response format is:
```json
[["wrb.fr", "r06xKb", "[<jobs-json>, null, <total>]", null, null, null, "generic"]]
```

with XSSI prefix `)]}'\n` followed by a length line.

---

## D. Historical evidence: `docs/decisions/0049` and `0050`

### D.1 ADR 0049 (2026-09-02)

> Google Tier-S discovery uses a dedicated `GoogleCareersAdapter`
> for the verified `Custom Google Careers` platform rather than
> generic HTML extraction.
>
> The adapter replays the anonymous BOQ endpoint used by the
> Google Careers frontend:
> `POST /about/careers/applications/_/HiringCportalFrontendUi/data/batchexecute`
> with `r06xKb` for search pagination. The request is
> form-encoded through the shared `HttpFetcher`; no browser, cookie,
> CSRF token, build id or referer is required by the observed
> endpoint.
>
> The positional response contract is pinned by tests: job
> id/title/apply URL, responsibilities, qualifications, company,
> locations, description, timestamps and minimum qualifications.
>
> Trade-offs: This is an internal, positional Google frontend
> contract rather than a documented public API. It may change.
> Strict schema validation and tests make breakage fail visibly
> rather than silently producing bad jobs.

### D.2 ADR 0050 (2026-09-02)

> Do not raise the scanner's global network defaults merely to
> accommodate Google. ... `scripts/run_google_careers_probe.sh`
> supplies a Google-only execution envelope:
> - global concurrency: 1;
> - per-domain concurrency: 1;
> - minimum interval: 1.25 s;
> - maximum pages: 200;
> - maximum requests/host and run: 220;
> ...

Both ADRs are **dated 2026-09-02**. They describe the design
intent. **They do not contain a saved Google API response or a
log of a successful execution.**

---

## E. Real evidence search

I checked the following locations for any real Google response
artifact:

```
data/cache/http/                   → contains 6 cached responses (sha256 keys only); cannot inspect without HTTP
data/cache/http_detail/             → contains 2 cached responses
data/raw/                           → empty
tests/fixtures/                     → no google_* fixture
output/test_runs/                   → no *google* log file
docs/reports/                       → no google_* report file
data/company_universe/              → contains master CSV, no Google-specific file
```

The only "Google" mentions in `output/test_runs/` are LLM provider
names (`google/gemini-3.5-flash-lite`).

**Conclusion: there is NO real saved Google Careers API response
artifact in the JobResearCHEF repository.** The adapter exists
and is tested with synthetic data, but there is no captured
artifact proving the adapter actually worked against a live
endpoint.

---

## F. Operator script: `scripts/run_google_careers_probe.sh`

This script is intended to run a live probe. It:

1. Resolves Google portal_id from DB
2. Preflights the adapter selection (zero-network adapter coverage check)
3. Calls `uv run research-agent scan-discover --portal-id <id>` with a Google-only network envelope
4. Calls `triage-pending --dry-run`, then `triage-pending` (live LLM call)
5. Calls `analyze-pending --dry-run`, then `analyze-pending` (live LLM call)
6. Prints a final summary

The script is **ready to run** but **has not been observed to have
completed** — there is no `output/test_runs/google_careers_probe_*.log`
file. The closest is `product_smoke_*.log` and
`tier_s_operational_sources_*.log` which are unrelated to Google.

---

## G. Per-question answers

| Question | Answer |
|---|---|
| Google adapter exists | **yes** — `src/research_agent/sources/ats/google_careers.py` (287 LOC) |
| Request construction implemented | **yes** — POST form-encoded to `/_/HiringCportalFrontendUi/data/batchexecute` with positional `f.req=<json>` |
| Parsing implemented | **yes** — positional array indices, pinned in tests (lines 41-53) |
| Offline tests | **yes** — 3 tests in `tests/test_google_careers_adapter.py`, all use `httpx.MockTransport` |
| Fixture reali salvate | **NO** — no `google_*` file in `tests/fixtures/` |
| Historic successful run evidence | **NO** — no `output/test_runs/google_*` file, no `docs/reports/google_*` file. The 2 ADRs dated 2026-09-02 describe intent only. |
| Current live verified | **NOT_CHECKED_OFFLINE_AUDIT** (this audit does not perform live verification) |
| Confidence that adapter still works today | **LOW** — the contract is positional and undocumented by Google. The persisted-query ID `r06xKb` is hardcoded and likely rotates at every Boq release. The legacy `data/cache/http/` does not appear to contain a captured Google response (sha256 keys cannot be inspected without HTTP). |

---

## H. Comparison with the previous audit (`google_NEEDS_EXTENSION.md`)

The previous batch2 audit marked Google as `NEEDS_EXTENSION` based
on 4 conservative probes that all returned either HTTP 400 (homepage)
or HTTP 200 with GraphQL error (Comet RPC with stale doc_id).
That audit found:

- Google careers is a Facebook Comet app using `batchexecute` RPC
- The persisted-query ID `r06xKb` was stale (returns "document not found")
- Browser-based doc_id extraction would be required for live access

The legacy `GoogleCareersAdapter` uses the same endpoint and the same
RPC ID. **The stale doc_id is exactly the failure mode the legacy
adapter would hit today.**

Two possibilities:
1. The doc_id `r06xKb` rotated between ADR date (2026-09-02) and the
   batch2 audit date (2026-09-05).
2. The legacy adapter was never actually exercised against a live
   endpoint in the legacy repository either.

Both possibilities point to the same conclusion: **there is no
positive evidence that the adapter works today.**

---

## I. Code-only verdict for the audit output

| Verdict | Value |
|---|---|
| Code present | yes (287 LOC) |
| Offline tested | yes (3 tests, MockTransport, no real fixtures) |
| Historic successful run evidence | NO (no log file, no real fixture) |
| Current live verified | NO (this audit cannot perform live verification) |
| Confidence | **LOW** |
| Why confidence is LOW | The positional contract is undocumented by Google. The persisted-query ID `r06xKb` was observed to be stale as recently as 2026-09-05. The legacy adapter has no live evidence in the repository. |
| Verdict text | `CODE_PRESENT — live behavior unverified` |

---

## J. What would it take to make the audit honest?

If we want to claim "Google adapter works today", we need:

1. A real saved response from Google Careers `/_/HiringCportalFrontendUi/data/batchexecute` (HTTP 200 with the `wrb.fr` envelope) — saved to `tests/fixtures/google_careers_search.json` and used by tests instead of MockTransport.
2. A real saved single-job detail response — saved to `tests/fixtures/google_careers_detail.json`.
3. A `output/test_runs/google_careers_probe_*.log` showing successful execution of `scripts/run_google_careers_probe.sh`.
4. A `docs/reports/google_careers_validation.md` summarizing the validation.

None of these exist today in the legacy repository. **Until they
do, the audit must say `CODE_PRESENT — live behavior unverified`.**

---

## K. Implication for the new architecture

If we ever want a Google source in the new `source_spec/v0.1`
declarative architecture:

- We would need either:
  - The persisted-query ID valid as of the new probe date, or
  - A new primitive to discover/refresh persisted-query IDs at runtime
- The positional array parsing cannot be expressed by the current
  v0.1 spec (no `array_index` extraction primitive).
- The HTML-section composition (Description/Responsibilities/Qualifications
  → joined HTML with `<h2>` headings) cannot be expressed by the
  current v0.1 spec (no multi-section composition primitive).

In other words, even if the doc_id were fresh, the legacy adapter's
positional + multi-section logic would need at least two new
v0.2 primitives to be representable declaratively.

The honest path forward is to **leave Google out of scope for
v0.1 and v0.2** until:
1. A fresh real response artifact exists.
2. The new primitives are designed and approved.

Both conditions must hold before claiming PASS_V01 for Google.
