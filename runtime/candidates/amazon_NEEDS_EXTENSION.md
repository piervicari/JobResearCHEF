# Amazon — `NEEDS_EXTENSION` (revised after offline re-evaluation)

## Status

This document supersedes the PASS_V01 verdict recorded in
`BATCH2_AMAZON_APPLE_REPORT.md`. Offline re-evaluation with the existing
fixtures (zero new HTTP) found two independent reasons Amazon cannot be
declared PASS_V01.

The old `candidates/amazon.json` has been moved to
`candidates/_archive/amazon.json.PASS_V01_then_revoked`. No active
`candidates/amazon.json` exists. No fake PASS spec is live.

## What was re-verified offline (zero HTTP, only existing fixtures)

### Finding 1: semantic content loss in the normalized job

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
`_try_paths` is defined at line 401 of `spec_executor.py`:

```python
def _try_paths(item: dict, paths: list[str]) -> Any:
    for p in paths:
        v = _get(item, p)
        if v:
            return v
    return None
```

Since `description` is truthy and present, the `basic_qualifications`
and `preferred_qualifications` fields are NEVER read. They sit in the
fallback list, unreachable.

**Empirical proof from the existing fixture (no new HTTP):**

Extracted the first job from `fixtures/amazon_catalog_page.json` via
the existing spec. Then searched for content unique to
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

### Finding 2: traversal cannot complete under the declared safety policy

| Quantity | Value |
|---|---|
| Backend hard cap on `hits` | 10000 |
| Page size | 10 |
| Number of data pages needed | 1000 |
| Plus empty-after-total probe (Amazon spec has `items_path_empty_after_total` rule) | +1 |
| **Total catalog sweep requests** | **1001** |
| `safety.max_requests_per_run` (Amazon spec, current) | **600** |

1001 > 600. A single safety-policy-compliant run can NEVER traverse the
full hard-cap range. The remaining 401 pages would be left unscanned
in every run, so the catalog is permanently incomplete under v0.1
safety constraints.

This is a configuration issue: bumping `max_requests_per_run` to 1001
would solve it. But the spec was frozen with 600 (chosen for
Mercedes-style catalogs), and Amazon's hard cap forces an oversized
budget. A source that cannot complete its own traversal under the
declared safety policy cannot honestly be marked
`traversal_complete_under_safety_policy = true`.

### Other findings (carried forward from batch 2)

- `locations[]` is a list of JSON-encoded strings; v0.1 can only
  extract the primary `normalized_location` field. Multi-location
  postings lose secondary locations.
- `posted_date` is "May 28, 2026" (free text); v0.1's `date_format`
  enum cannot parse it; the spec sets `publication_date_path: null`.
- Amazon exposes locale via URL path (`/en/`, `/de/`), not via
  query/body; the `language` block is a no-op.

## Verdict (revised)

| Field | Value |
|---|---|
| primary_verdict | **`NEEDS_EXTENSION`** |
| contract_fit | PASS_V01 (the spec syntax parses and the primitive operations exist) |
| semantic_complete | **false** (basic+preferred qualifications lost) |
| traversal_complete_under_safety_policy | **false** (1001 needed vs 600 allowed) |
| authoritative_for_closed | false (was already false: filtered_catalog) |
| browser_required | false |

## Extension pressure

### Capability 1: compose multiple text paths

- **missing_capability**: a primitive that concatenates or unions
  text from multiple paths into a single normalized field, with
  per-path strip_html / join-separator configuration.
- **why v0.1 cannot express it**: `_try_paths` returns the first
  truthy value, so `fallback_paths` is unreachable when the primary
  path is truthy. The spec has no way to say "join `description`,
  `basic_qualifications`, and `preferred_qualifications` in this
  order".
- **exact real evidence** (no HTTP, just the saved fixture):
  the normalized job for `amazon_catalog_page.json` job 0 contains
  the substring `'1+ years of Windows Server'` only zero times; the
  raw `basic_qualifications` field contains it once. The information
  is present upstream and absent downstream.
- **proposed_generic_primitive** (NOT implemented):
  ```json
  "description": {
    "path": "description",
    "shape": "string",
    "join_paths": [
      {"path": "basic_qualifications"},
      {"path": "preferred_qualifications"}
    ],
    "join_separator": "\n\n",
    "strip_html": true
  }
  ```
  Runtime would read each path, strip HTML, concatenate with
  separator.
- **could_other_sources_reuse_it**: yes. Any source that splits
  job description into multiple sibling fields (custom ATSes,
  greenhouse with separate requirements, lever with lists, etc.)
  would benefit. Also useful for sources that put a summary in
  one field and details in another.
- **alternative_without_schema_change**: no. The spec cannot say
  "concatenate these paths" anywhere.
- **complexity**: low. Most plumbing already exists in
  `extract_description` for `list_of_blocks` shape.

### Capability 2: extract qualifications as a separate normalized field

- **missing_capability**: a primitive that, given a sibling path
  whose content should land in the `qualifications` normalized
  field (not `description`), declares the secondary path.
- **why v0.1 cannot express it**: `extract_description` with
  `shape="string"` always puts everything in `description` and
  leaves `qualifications=""`. With `shape="list_of_blocks"` you
  can split via `tasks_relative_key` + `qualifications_relative_key`
  but that requires the payload to actually be a list of objects
  with those keys (Mercedes-style). Amazon's payload is flat
  fields, not a list.
- **proposed_generic_primitive** (NOT implemented): extend
  `extraction.description` with an optional `qualifications_path`
  (single dotted path) that, when present, populates
  normalized `qualifications` instead of leaving it empty.
  Combined with capability 1, you could declare:
  - description_path = "description" (main body)
  - qualifications_path = "basic_qualifications" (then "preferred_qualifications" via another fallback? or join into one qualifications field?)
- **could_other_sources_reuse_it**: yes. Same class of ATS that
  splits the job text.
- **alternative_without_schema_change**: no.
- **complexity**: low.

### Capability 3: raise `max_requests_per_run` per spec

- This is a config-level change, not a primitive. The runtime
  already accepts any integer. Amazon's spec would simply need
  `safety.max_requests_per_run: 1001` to satisfy
  `traversal_complete_under_safety_policy`. This is NOT a v0.1
  contract change — it is a per-source tuning.
- The re-evaluation report flags this as a separate semantic
  finding because the **original** spec was tuned to 600 and that
  tuning made the source unable to complete. Setting it higher
  is the obvious fix; documenting why it had to be raised is the
  point.

## What was NOT changed

- No HTTP traffic. Zero new requests.
- `runtime/source_spec.schema.json` unchanged.
- `runtime/spec_executor.py` unchanged.
- `runtime/job.schema.json` unchanged.
- `runtime/sources/mercedes.json` unchanged.
- `runtime/sources/nvidia.json` unchanged.
- The old `candidates/amazon.json` was renamed to
  `_archive/amazon.json.PASS_V01_then_revoked` and is no longer
  a live spec.
- No fake `candidates/amazon.json` was recreated.

## Safety

The original Amazon discovery run produced no 429, no 403, and no
CAPTCHA. All 6 HTTP requests were answered 200 (or 302 for the
official-URL redirect probe, which is intentional, not an error).
Pacing was 5–6 seconds between requests. No retry was needed.

## Fixtures preserved

All Amazon fixtures remain on disk. They are valid real captured
responses and may be reused when Amazon is later represented under
v0.2 with the proposed primitives (or a v0.1-compatible workaround).

- `fixtures/amazon_catalog_page.json` — 92,667 bytes (real, offset=0)
- `fixtures/amazon_catalog_page2.json` — 98,568 bytes (real, offset=10)
- `fixtures/amazon_catalog_empty.json` — 135 bytes (real, offset=10000, error sentinel)
