# Batch 2 — Amazon & Apple discovery report (REVISED)

**Source spec frozen version:** `source_spec/v0.1`
**Generic executor:** `runtime/spec_executor.py` (unmodified)
**Schema:** `runtime/source_spec.schema.json` (unmodified)
**Job schema:** `runtime/job.schema.json` (unmodified)
**Date (initial):** 2026-09-05
**Date (revision):** 2026-09-05 (same day, offline re-evaluation)

## Revision note

The initial version of this report (created immediately after batch-2
discovery) declared Amazon as **`PASS_V01`** with documented v0.1
limitations. An offline re-evaluation with the existing fixtures
(zero new HTTP traffic) found two independent findings that invalidate
that verdict:

1. **semantic_complete = false**: the normalized Amazon job loses
   `basic_qualifications` and `preferred_qualifications` text because
   `spec_executor.py::extract_description()` uses `_try_paths`, which
   returns the FIRST truthy path. When `description` is truthy,
   the fallback paths (`basic_qualifications`, `preferred_qualifications`)
   are unreachable.
2. **traversal_complete_under_safety_policy = false**: the Amazon
   spec declares `safety.max_requests_per_run = 600`, but a full
   sweep of the 10000-hit hard cap requires 1001 catalog requests
   (1000 data pages + 1 empty-after-total probe).

These two findings are documented in
`runtime/candidates/amazon_NEEDS_EXTENSION.md`. The active
`candidates/amazon.json` (PASS_V01) has been moved to
`candidates/_archive/amazon.json.PASS_V01_then_revoked`.

Additionally, the Apple catalog_scope claim was re-checked offline
against the saved fixture: the fixture contains jobs from 16
countries, not "USA only" as the initial report stated. The
`postLocation-USA` filter claim is not verifiable from the saved
fixture alone; catalog_scope = `unresolved`.

No frozen contract file was modified to reach these conclusions.

---

## Summary table (REVISED)

| Company | Backend | Primary verdict | contract_fit | semantic_complete | traversal_complete_under_safety_policy | authoritative_for_closed | browser_required | v0.1 valid | New primitive | Live requests | 403 | 429 |
|---|---|---|---|---|---|---|---|---|---|---|---:|---:|
| **Amazon** | Amazon proprietary `amazon.jobs` JSON API | **`NEEDS_EXTENSION`** | PASS_V01 | **false** | **false** | false (filtered_catalog, hard cap at 10000) | false | partial (syntax OK, semantics broken) | yes (join_paths or qualifications_path) | 6 | 0 | 0 |
| **Apple** | Apple proprietary CSRF-guarded JSON search API | **`NEEDS_EXTENSION`** | NEEDS_EXTENSION | unknown (description only `jobSummary` short, full description in HTML hydration blob, not probed) | unknown | unknown | unknown | **no** | yes (page_number, bootstrap, session cookie) | 5 | 0 | 0 |

## Metrics (REVISED)

| Metric | Value |
|---|---|
| **Amazon revised verdict** | `NEEDS_EXTENSION` |
| **Amazon semantic_complete** | **false** |
| **Amazon traversal_complete_under_safety_policy** | **false** |
| **Amazon authoritative_for_closed** | false |
| **Apple catalog_scope** | **`unresolved`** |
| **Apple countries observed in fixture** | 16 countries: Austria, Belgium, Canada, France, Germany, India, Italy, Korea (Republic of), Netherlands, Spain, Sweden, Switzerland, Türkiye, United Arab Emirates, United Kingdom, United States of America |
| **Apple semantic_complete** | unknown |
| **Apple browser_required** | unknown |
| `PASS_V01` count (revised) | **0** in batch-2 (Mercedes, NVIDIA, Microsoft remain PASS_V01 from earlier batches) |
| `NEEDS_EXTENSION` count (revised) | **2** (Amazon, Apple) |
| `CUSTOM_REQUIRED` count | 0 |
| `UNRESOLVED` count (Apple catalog_scope) | 1 |
| `SAFETY_ABORT` count | 0 |
| **Modifications to `source_spec.schema.json`** | **0** |
| **Modifications to `spec_executor.py`** | **0** |
| **Modifications to `job.schema.json`** | **0** |
| **Modifications to `sources/mercedes.json`** | **0** |
| **Modifications to `sources/nvidia.json`** | **0** |
| Frozen regression tests (42) | **pass** (42/42) |
| Batch1 candidate tests (24) | **pass** (24/24) |
| Batch2 revised tests (new file) | **pass** |
| **HTTP 403 total** | **0** |
| **HTTP 429 total** | **0** |
| **Total live HTTP requests** | **11** (6 Amazon + 5 Apple) — unchanged |
| **New HTTP requests added during revision** | **0** |

---

## Amazon — revised analysis

### Empirical finding 1: semantic content loss in the normalized job

The Amazon catalog payload contains three distinct text fields per item:

| Field | Length (job 0 in fixture) | Content type |
|---|---|---|
| `description` | 5807 chars | full job description (responsibilities, team, benefits, about) |
| `basic_qualifications` | 646 chars | "1+ years of Windows Server technologies: AD, DFS, Print Services, SCCM experience..." |
| `preferred_qualifications` | 1880 chars | "2+ years of computer networking experience, Experience supporting video conference and teleconference equipment..." |

The source spec at the time declared:
- `extraction.description.path = "description"`
- `extraction.description.fallback_paths = ["basic_qualifications", "preferred_qualifications"]`
- `extraction.description.shape = "string"`

`spec_executor.py::extract_description()` calls `_try_paths(item, [primary] + fallback_paths)`
which **returns the FIRST truthy value** (it does NOT concatenate).

```python
def _try_paths(item: dict, paths: list[str]) -> Any:
    for p in paths:
        v = _get(item, p)
        if v:
            return v
    return None
```

Since `description` is truthy and present, the `basic_qualifications`
and `preferred_qualifications` fields are NEVER read.

**Empirical proof (zero new HTTP, just saved fixtures)**:

Extracted the first job from `fixtures/amazon_catalog_page.json` via
the (now archived) spec. Then searched for content unique to
`basic_qualifications` and `preferred_qualifications` in the resulting
normalized job:

| Unique marker | In raw `basic_qualifications` | In raw `description` | In normalized `description` | In normalized `qualifications` |
|---|---|---|---|---|
| `'1+ years of Windows Server'` (basic) | yes | no | **no** | **no** |
| `'SCCM'` (basic) | yes | no | **no** | **no** |
| `'teleconference equipment'` (preferred) | yes | no | **no** | **no** |

The normalized job has `description` length = 5399 chars (HTML-stripped
from the 5807-char `description` field) and `qualifications` length = 0.

**Impact**: 2526 chars of semantically-relevant text
(`basic_qualifications` + `preferred_qualifications`) are dropped from
the normalized job on every Amazon item. For the project's downstream
classification use case, this is unacceptable: a posting that lists
"5+ years of Windows Server / SCCM / DNS / DHCP / OSI Model / TCP/IP"
plus "experience with video conference and teleconference equipment"
contains cybersecurity-relevant skill signals that the classifier
needs. Losing them defeats the entire pipeline.

### Empirical finding 2: traversal cannot complete under the declared safety policy

| Quantity | Value |
|---|---|
| Backend hard cap on `hits` | 10000 |
| Page size | 10 |
| Number of data pages needed | 1000 |
| Plus empty-after-total probe (Amazon spec has `items_path_empty_after_total` rule) | +1 |
| **Total catalog sweep requests** | **1001** |
| `safety.max_requests_per_run` (Amazon spec) | **600** |

1001 > 600. A single safety-policy-compliant run can NEVER traverse
the full hard-cap range. The remaining 401 pages would be left
unscanned in every run, so the catalog is permanently incomplete
under v0.1 safety constraints.

This is a configuration issue, not a primitive issue. Bumping
`max_requests_per_run` to 1001 in the spec would solve it. The
re-evaluation flags this as a separate semantic finding because the
*original* spec was tuned to 600 (chosen for Mercedes-style catalogs)
and that tuning made the source unable to complete.

### Documented v0.1 limitations for Amazon (carried forward from batch-2)

- `locations[]` is a list of JSON-encoded strings; v0.1 can only
  extract the primary `normalized_location` field. Multi-location
  postings lose secondary locations.
- `posted_date` is "May 28, 2026" (free text); v0.1's `date_format`
  enum cannot parse it; the spec sets `publication_date_path: null`.
- Amazon exposes locale via URL path (`/en/`, `/de/`), not via
  query/body; the `language` block is a no-op.

### Amazon verdict (revised)

| Field | Value |
|---|---|
| primary_verdict | **`NEEDS_EXTENSION`** |
| contract_fit | PASS_V01 (the spec syntax parses and the primitive operations exist) |
| semantic_complete | **false** |
| traversal_complete_under_safety_policy | **false** |
| authoritative_for_closed | false (was already false: filtered_catalog) |
| browser_required | false |

### Extension pressure for Amazon

Documented in `candidates/amazon_NEEDS_EXTENSION.md`:

- **Capability 1**: compose multiple text paths. The spec currently
  has no way to say "join `description`, `basic_qualifications`, and
  `preferred_qualifications` in this order". A primitive
  `join_paths` (list of paths) with per-path `strip_html` and a
  shared `join_separator` would solve it.
- **Capability 2**: extract qualifications as a separate normalized
  field via a sibling `qualifications_path` (single dotted path)
  that populates normalized `qualifications` instead of leaving it
  empty.
- **Capability 3**: per-spec `safety.max_requests_per_run` tuning.
  Not a primitive change. Just a config decision. Amazon needs
  ≥ 1001.

---

## Apple — revised analysis

### Empirical finding: catalog_scope = unresolved

The initial batch-2 report stated that the Apple search request body
included `postingpostLocation:["postLocation-USA"]` and that
`totalRecords=6124` represented USA-only jobs. The saved fixture
contradicts this: `apple_catalog_page.json` contains 20 jobs from 16
different countries.

**Countries observed in the saved fixture**:

Austria, Belgium, Canada, France, Germany, India, Italy, Korea
(Republic of), Netherlands, Spain, Sweden, Switzerland, Türkiye,
United Arab Emirates, United Kingdom, United States of America.

We do not invent an explanation for the contradiction. The plausible
hypotheses are:

1. The request body I sent did NOT actually include the
   `postingpostLocation` filter (filter was lost in shell quoting
   or the body sent was a different shape than I remember).
2. The filter was sent but Apple ignored it (returns global
   results regardless).
3. The cookie/session state was reused from a previous request
   that did not have the filter.

The saved fixture is what it is. `totalRecords=6124` cannot be
interpreted as "USA only" without independent verification of the
filter. **`catalog_scope = unresolved`** until a reproducible
filter is exercised and the response confirmed to be filtered.

### Carried-forward findings (batch-2)

- Pagination is `page=N` (1-based, integer, step=1, page_size=20).
  Observed with 4 probes: `page=1→20 items, page=2→20 items,
  page=307→4 items, page=308→0 items`. `totalRecords=6124` constant.
- CSRF bootstrap required: `GET /api/v1/CSRFToken` returns
  `X-Apple-CSRF-Token` header + `Set-Cookie: jobs, jssid,
  AWSALBAPP-0`. Without this, `POST /api/v1/search` would return
  401/403.
- No JSON detail endpoint: full description lives in HTML
  hydration blob of `https://jobs.apple.com/en-us/details/{id}-{slug}`.

### Apple verdict

| Field | Value |
|---|---|
| primary_verdict | `NEEDS_EXTENSION` |
| contract_fit | NEEDS_EXTENSION (page_number strategy not in v0.1, bootstrap step not in v0.1, cookie persistence not in v0.1) |
| semantic_complete | unknown (no full description accessible via the JSON API) |
| traversal_complete_under_safety_policy | unknown (depends on whether 6124 is USA or global; if global, ~6124/20 = 307 pages, ~308 requests + 1 bootstrap = 309, fits 600 easily; if USA, same number; if only part of global, much smaller) |
| authoritative_for_closed | unknown |
| browser_required | unknown (detail page HTML scraping not probed) |
| catalog_scope | **unresolved** (filter claim contradicted by fixture) |

### Extension pressure for Apple (carried forward)

- **page_number pagination**: 1-based integer, step=1.
- **bootstrap step**: preliminary CSRF fetch + token extraction.
- **session cookie persistence**: cross-cutting.

These are the same extensions noted in the original Apple
NEEDS_EXTENSION doc.

---

## Frozen regression verification (post-revision)

| Asset | Status |
|---|---|
| `runtime/source_spec.schema.json` | unchanged |
| `runtime/spec_executor.py` | unchanged |
| `runtime/job.schema.json` | unchanged |
| `runtime/sources/mercedes.json` | unchanged |
| `runtime/sources/nvidia.json` | unchanged |
| `runtime/validate_specs.py` | unchanged |
| `runtime/test_spec_executor.py` | unchanged |
| `runtime/test_spec_executor.py` execution | **42/42 PASS** |
| `runtime/test_candidates_batch1.py` execution | **24/24 PASS** |

The revised test file is `test_candidates_batch2_revised.py`. It
does NOT replace `test_candidates_batch2.py` (which still references
the archived Amazon spec) but is the authoritative test for the
revised verdicts. Both files coexist; `test_candidates_batch2.py`
will fail because `candidates/amazon.json` no longer exists. The
revised file is the live one.

Verified by `FrozenRegressionTests` in `test_candidates_batch2_revised.py`:

- `test_frozen_executor_tests_still_pass` — re-runs `test_spec_executor.py`, asserts exit 0 and ≥ 42 tests.
- `test_batch1_candidates_tests_still_pass` — re-runs `test_candidates_batch1.py`, asserts exit 0 and ≥ 24 tests.
- `test_executor_did_not_change` — confirms `spec_executor.py` docstring still declares v0.1 scope.
- `test_schema_did_not_change_version` — confirms `paging.strategy` is still `const "offset"`.
- `test_spec_executor_try_paths_returns_first_truthy` — locks in the runtime's documented behaviour that motivates the Amazon NEEDS_EXTENSION verdict. This protects the finding from accidental silent changes in the future.

## What was changed during revision

- `candidates/amazon.json` → `candidates/_archive/amazon.json.PASS_V01_then_revoked` (archived, not deleted, so the spec text remains available for reference).
- `candidates/amazon_NEEDS_EXTENSION.md` (new) — full Amazon NEEDS_EXTENSION documentation.
- `test_candidates_batch2_revised.py` (new) — revised tests with semantic-loss and traversal-budget findings.
- This report (rewritten) — summary table now shows the revised verdicts.

## What was NOT changed

- No HTTP traffic. Zero new requests during revision.
- `runtime/source_spec.schema.json` unchanged.
- `runtime/spec_executor.py` unchanged.
- `runtime/job.schema.json` unchanged.
- `runtime/sources/mercedes.json` unchanged.
- `runtime/sources/nvidia.json` unchanged.
- The archived `candidates/amazon.json` is preserved as a record of the original PASS_V01 attempt; it is not loaded by any active validator path.
- No fake `candidates/amazon.json` was created.

## Suggested next steps

1. Treat Amazon and Apple as documented extension pressure for v0.2.
2. When a third source also exhibits `basic_qualifications` /
   `preferred_qualifications` (or similar multi-text-field payload),
   the proposed `join_paths` / `qualifications_path` primitive has
   two-evidence justification and can move from "documented" to
   "implemented".
3. For Apple specifically, the catalog_scope must be re-verified
   with a fresh probe that exercises the `postLocation-USA` filter
   and checks the response is USA-only. Until that probe runs,
   `totalRecords=6124` cannot be claimed to mean "USA only".
4. Continue discovery on ATSs known to use `?page=N` (Indeed,
   LinkedIn) — these would naturally exercise the page_number
   primitive if v0.2 adds it.
