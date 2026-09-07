# Migration Plan — from JobResearCHEF to a hybrid runtime

> **Audit-only document. Corrected post-reuse-audit.** Pure
> plan. No code is written. The goal is to propose a sequence of
> phases that maximizes reuse of JobResearCHEF components while
> adopting the new `source_spec/v0.1` declarative model.

The recommended final architecture is **HYBRID**:
- A `source_spec/v0.1` runtime for new sources where the protocol
  is simple and the wire is documented.
- Existing JobResearCHEF Python adapters for sources where the
  v0.1 contract is awkward.
- Both write into the same DB schema. Same dedup, lifecycle,
  dashboard, LLM classifier.

This is justified in section 1. Phases below.

The corrections in this document vs the previous version:

- **Phase 1** is tightened: only ACTIVE_PASS_CANDIDATE + FROZEN_PASS_SPEC
  sources are used in the test. NEEDS_EXTENSION / UNRESOLVED /
  REVOKED sources are excluded.
- **Phase 3** wording is corrected: legacy adapters stay legacy
  adapters. `DeclarativeSourceAdapter` is a NEW implementation of
  the same contract, not a wrapper that converts legacy code.
- **Phase 1** transport bridge explicitly lists what v0.1
  supports, and does NOT anticipate v0.2 primitives.

---

## 0. Audit (DONE)

- **What changes**: nothing. Pure reading of both repos.
- **What doesn't change**: everything. No file modified.
- **Risk**: zero. This is documentation only.
- **Test of success**: 5 audit files exist in `runtime/reuse_audit/`
  + `EXTENSION_PRESSURE_REGISTRY.md` updated. JobResearCHEF files
  unchanged (verified by `git status` clean). `runtime/` frozen
  files unchanged (verified by mtime + 121 PASS tests).

---

## 1. Source status reference (used by Phase 1)

The Phase 1 transport bridge must work against the **active valid
v0.1 source specs only**. As of this audit:

| Source | State | File | Phase 1 inclusion |
|---|---|---|---|
| Mercedes-Benz | FROZEN_PASS_SPEC | `runtime/sources/mercedes.json` | **YES** |
| NVIDIA | FROZEN_PASS_SPEC | `runtime/sources/nvidia.json` | **YES** |
| Microsoft | ACTIVE_PASS_CANDIDATE | `runtime/candidates/microsoft.json` | **YES** |
| Cloudflare | ACTIVE_PASS_CANDIDATE | `runtime/candidates/cloudflare.json` | **YES** |
| Amazon | REVOKED / ARCHIVED | `runtime/candidates/_archive/amazon.json.PASS_V01_then_revoked` | **NO** |
| Apple | NEEDS_EXTENSION | `runtime/candidates/apple_NEEDS_EXTENSION.md` | **NO** |
| Google | NEEDS_EXTENSION | `runtime/candidates/google_NEEDS_EXTENSION.md` | **NO** |
| Meta | UNRESOLVED | `runtime/candidates/meta_UNRESOLVED.md` | **NO** |

Phase 1 MUST exclude Amazon (archived), Apple/Google/Meta (NEEDS_EXTENSION
or UNRESOLVED). The test suite of Phase 1 succeeds only if the
4 PASS sources are correctly bridged.

---

## 2. Phase 1 — wire the runtime to the existing fetcher (corrected)

**Goal**: make `runtime/spec_executor.py::render_catalog_request`
and `render_detail_request` produce HTTP request objects that
`JobResearCHEF.pipeline.http.HttpFetcher` can consume directly.

**What changes** (minimal, source-agnostic):

- New module `runtime/transport.py` (or a small extension to
  `runtime/spec_executor.py` — but `spec_executor.py` is frozen, so
  the new module lives separately and is the bridge):
  ```python
  # runtime/transport.py
  from dataclasses import dataclass

  @dataclass
  class TransportRequest:
      method: str
      url: str
      headers: dict[str, str]
      form_body: dict[str, str] | None = None  # for application/x-www-form-urlencoded
      json_body: dict | None = None            # for application/json

  def render_as_transport_request(spec: dict, kind: str, value: Any, variables: dict | None = None) -> TransportRequest:
      """
      kind = 'catalog' or 'detail'
      value = the page_value (catalog) or stable_id (detail)
      Returns a TransportRequest that:
        - for GET: url has query params injected
        - for POST with body_path: body has the offset written at the declared path
        - for POST with json_body: body is the JSON template
      Headers come from request.headers + templates interpolated.
      """
      ...
  ```
- The bridge is **purely a serializer** between two existing
  representations. It does NOT issue HTTP. It does NOT introduce
  any new primitive. It does NOT touch v0.1 spec semantics.

**What doesn't change**:
- `runtime/spec_executor.py` stays source-agnostic and frozen.
- `runtime/source_spec.schema.json` stays frozen.
- `JobResearCHEF.pipeline.http.HttpFetcher` stays as-is. The
  bridge produces something the HttpFetcher already understands
  (URL, method, headers, form_body / json_body).

**What v0.1 actually supports — explicit list**:

The bridge must support exactly what v0.1 supports, no more:

| v0.1 feature | What the bridge produces |
|---|---|
| `request.method = "GET"` | `TransportRequest(method="GET", url=..., headers=...)` |
| `request.method = "POST"` + `body: {...}` + `inject.target: "body_path"` | `TransportRequest(method="POST", url=..., headers=..., json_body=<injected>)` |
| `request.method = "POST"` + `body: {...}` + `inject.target: "query_param"` | `TransportRequest(method="POST", url=..., headers=..., json_body=<injected>)` (the page_value goes into a query param; the body is unchanged) |
| `detail.method` + `detail.interpolation.target: "query_param"` | `TransportRequest(method=..., url=<id injected>, ...)` |
| `detail.interpolation.target: "body_path"` | `TransportRequest(method=..., json_body=<id injected>, ...)` |

**What v0.1 does NOT support — explicitly excluded from Phase 1**:

| v0.1 limitation | Phase 1 action |
|---|---|
| No `request.body_encoding: "form"` | Bridge uses `json_body` for all POST bodies. Apple/Google/Meta cannot be bridged in Phase 1 — they need v0.2. |
| No `paging.strategy: "page_number"` | Bridge uses `offset` only. Apple/Google/Radancy/SuccessFactors/Oracle are excluded. |
| No `request.bootstrap` | Bridge assumes no bootstrap. Apple/Workday/Oracle are excluded. |
| No cookie persistence | Bridge does not store or replay cookies. Apple is excluded. |

**Test of success**:

For each of the 4 PASS sources (Mercedes, NVIDIA, Microsoft,
Cloudflare):

1. The bridge produces a `TransportRequest` whose URL, method,
   headers, and body match what a real HTTP client would send.
2. The `HttpFetcher` accepts the `TransportRequest` (it already
   takes `url`, `method`, `headers`, `form_body`, `json_body`).
3. A round-trip test: for each fixture in `runtime/fixtures/`,
   the bridge output, when fed to the HttpFetcher, would produce
   the same HTTP wire request that originally captured the
   fixture.

The Phase 1 test MUST NOT include:

- Apple (`fixtures/apple_catalog_page.json`) — needs bootstrap + page_number
- Google — no fixture
- Meta — no fixture, only error envelope
- Amazon — REVOKED, would fail completeness anyway

**Risk**: low. The new module is purely a serializer between two
existing data shapes.

---

## 3. Phase 2 — lift dedup + lifecycle + normalizer into the new pipeline (zero schema change)

**Goal**: when the runtime extracts a normalized `Job`, hand it
to the legacy `pipeline/dedup.py` + `pipeline/normalizer.py` for
canonicalization, then `pipeline/lifecycle.py` for persistence
into `SourceJob`.

**What changes**:
- New module `runtime/persistence.py`:
  ```python
  def persist_normalized_jobs(
      engine: Engine,
      scan_run_id: int,
      portal_id: int,
      spec: dict,                       # source_spec/v0.1
      normalized_jobs: list[dict],      # job.schema.json-shaped
      raw_payloads: list[dict],        # original wire response
  ) -> ProcessingSummary:
      ...
  ```
  This function:
  1. Calls `pipeline/normalizer.normalize_job(RawJob(...))` on each item.
  2. Calls `pipeline/dedup.canonical_fingerprint(...)` to assign `canonical_job_id`.
  3. Calls `pipeline/lifecycle.process_scan_results(...)` to update `SourceJob` rows.
  4. Sets `SourceJob.adapter = "<spec.company.id>_v0.1"` so the dashboard can distinguish.

**What doesn't change**:
- The DB schema (`SourceJob` row already has all needed fields).
- The legacy dedup logic (it operates on `RawJob`; we convert from
  the new normalized dict to `RawJob`).
- The legacy lifecycle (`process_scan_results`).

**Risk**: low. The conversion from `job.schema.json`-shape to
`RawJob` is mechanical.

**Test of success**:
- For each PASS_V01 spec (Mercedes, NVIDIA, Microsoft, Cloudflare),
  the function persists all normalized jobs to DB with correct
  `source_job_id`, `apply_url`, `description`, `source_payload_sha256`.
- `canonical_fingerprint` produces a stable hash for the same
  job across runs.
- Dedup correctly identifies the same job across Mercedes+NVIDIA
  if a job appears in both (it won't, but the dedup logic must work).

---

## 4. Phase 3 — introduce `DeclarativeSourceAdapter` (corrected)

> **CORRECTION vs the previous plan**: this phase does NOT
> "wrap each legacy ATS adapter as DeclarativeSourceAdapter".
> The legacy Python adapters stay as they are. The new
> `DeclarativeSourceAdapter` is a NEW implementation of the same
> `SourceAdapter` Protocol, fed by a `source_spec/v0.1` JSON file.

**Goal**: introduce a uniform `SourceAdapter` interface that can
be implemented by either (a) a legacy Python adapter or (b) a
declarative `source_spec/v0.1` runner. Both produce
`AdapterScanResult` and are stored in the same `AdapterRegistry`.

**Architecture (corrected wording)**:

```
AdapterRegistry
├── legacy Python SourceAdapters       (AshbyAdapter, GreenhouseAdapter, LeverAdapter,
│                                       SmartRecruitersAdapter, WorkdayAdapter, OracleRecruitingCloudAdapter,
│                                       PhenomAdapter, RadancyAdapter, SuccessFactorsRmkAdapter,
│                                       AvatureAdapter, GenericOfficialHtmlAdapter, GoogleCareersAdapter)
└── DeclarativeSourceAdapter(s)        (new, one per active source_spec/v0.1 JSON)
```

The legacy adapters stay legacy adapters. `DeclarativeSourceAdapter`
is added as a SIBLING, not as a wrapper around them.

**What changes**:
- New class `runtime/declarative_adapter.py`:
  ```python
  class DeclarativeSourceAdapter:
      name = "<spec.company.id>_v01_declarative"
      bulk_catalog = True  # heuristic from spec
      
      def supports(self, target: PortalTarget) -> bool:
          return target.normalized_jobs_url == self._spec["request"]["url"]
      
      async def scan(self, target, context):
          results = []
          for offset in pagination_iterator(self._spec, total=???):
              fetch_request = render_as_transport_request(self._spec, "catalog", offset)
              response = await context.fetch(fetch_request)
              items, total = extract_page(self._spec, response.json())
              ...
          return AdapterScanResult(...)
  ```
- The `target` interface is legacy-shaped (`PortalTarget`). We
  need a converter from `(spec, company_id)` to `PortalTarget`.

**What doesn't change**:
- The 11 legacy Python adapters stay as-is.
- The legacy `AdapterRegistry.select()` already iterates adapters
  in priority order.

**Risk**: medium. The `target` interface is legacy-shaped
(`PortalTarget`) — we need a converter from `(spec, company_id)`
to `PortalTarget`. The fields don't perfectly align. The
`normalizes_jobs_url` is the closest analog to `request.url`.

**Test of success**:
- For each of the 4 PASS sources (Mercedes, NVIDIA, Microsoft,
  Cloudflare): `DeclarativeSourceAdapter.scan()` produces the
  same `AdapterScanResult` as the equivalent Python adapter
  (verified by running both on the same saved fixture).
- The `AdapterRegistry.select()` correctly dispatches to the right
  adapter per `PortalTarget`.

---

## 5. Phase 4 — verify equivalence between Declarative and Legacy (where applicable)

**Goal**: prove the declarative approach produces equivalent
output to legacy adapters for sources that have BOTH paths
available.

**What changes**:
- For each source that has BOTH a declarative spec AND a legacy
  Python adapter, run both and diff the outputs.
- Available candidates:
  - GreenhouseAdapter (legacy) vs Cloudflare (declarative, same wire) — same wire, different runtime.
  - SmartRecruitersAdapter (legacy) vs Mercedes/Microsoft (declarative, same wire for Microsoft/Eightfold; not for SmartRecruiters though).
- This is a TEST-ONLY phase. No production change.

**What doesn't change**:
- Source specs.
- Legacy adapters.

**Risk**: medium. Real-world fixtures may reveal spec gaps that
the legacy adapter papers over.

**Test of success**:
- `test_declarative_vs_legacy_equivalence.py` — for each migrated
  source, the normalized jobs from the legacy adapter and the
  declarative adapter are identical (deep diff on all fields).

---

## 6. Phase 5 — leave non-v0.1 sources to the legacy adapter; reserve Hermes discovery for unresolved

**Goal**: the new architecture is hybrid by design. Sources that
are awkward declaratively (Phenom, Radancy, SuccessFactors,
Avature, GenericOfficialHtml, Google Careers, Meta) stay on the
legacy adapters. New sources go through Hermes discovery →
declarative spec.

**What changes**:
- A short document (in `docs/`) listing which sources are
  declarative and which are legacy, with the rationale.
- The Hermes discovery agent is called only for sources that are
  not yet covered by either the declarative spec set or the legacy
  adapter set.

**What doesn't change**:
- The legacy adapter code.
- The legacy operator flow.

**Risk**: low. This is mostly documentation and process.

**Test of success**:
- Every PASS_V01 source has either a declarative spec OR a legacy
  Python adapter (or both, during the migration).
- No source is silently dropped.

---

## 7. Phase 6 — design v0.2 primitives using the cumulative evidence

**Goal**: design the v0.2 contract using all evidence so far:
- 121 PASS tests across 4 batches
- 11 legacy JobResearCHEF adapters
- `EXTENSION_PRESSURE_REGISTRY.md` (corrected)

**What changes**:
- New `runtime/source_spec.schema.json` (v0.2) — but this is the
  ONLY frozen file that changes. The new schema adds primitives
  for the top-ranked v0.2 candidates:
  1. `page_number` pagination (**HIGH_CONFIDENCE_V02**)
  2. `bootstrap_request` block (**HIGH_CONFIDENCE_V02**)
  3. `load-more / cursor_link` pagination (**MEDIUM_CONFIDENCE_V02**)
  4. `html-embedded-json` extraction (**MEDIUM_CONFIDENCE_V02**)

**What doesn't change**:
- `runtime/spec_executor.py` evolves alongside, but stays
  source-agnostic.
- `runtime/job.schema.json` is stable.
- The legacy codebase continues to work independently.

**Risk**: high. v0.2 is a contract change. Every consumer must
re-validate. Mitigate by:
- Keeping v0.1 as a valid subset of v0.2 (backward-compatible).
- Running all 121 PASS tests on v0.2 before declaring it stable.
- Re-running all 11 legacy Python adapters to confirm no regression.

**Test of success**:
- v0.2 contract documented.
- New primitives have at least 1 LIVE_FIXTURE or 2
  HISTORIC_LEGACY_FIXTURE evidence sources each.
- All v0.1 specs still validate against v0.2 schema.
- All v0.1 runtime tests still PASS on v0.2.

---

## 8. Phase 7 — wire dashboard + AI + notifications to the unified output

**Goal**: the existing Streamlit dashboard and free-only LLM
classifier already work on the `SourceJob` schema. The new
declarative runs just produce the same schema. No changes needed
to the dashboard or AI.

**What changes**:
- A small dashboard filter ("extraction_mode: declarative |
  legacy") so operators can distinguish.
- An AI analysis log entry: `model_used_for_extraction: "spec_executor
  v0.1" vs "GreenhouseAdapter vN"`.

**What doesn't change**:
- The Streamlit dashboard itself.
- The LLM classifier.
- The Telegram / notifications code (if any).

**Risk**: zero. Pure dashboard polish.

**Test of success**:
- The dashboard shows both extraction modes correctly.
- No LLM regression.

---

## 9. Phase 8 — decommission

**Goal**: as more sources are migrated to declarative, retire
the corresponding legacy adapters. Keep the rest.

**What changes**:
- Once Cloudflare (Greenhouse) is fully declarative, the legacy
  `GreenhouseAdapter` can be deprecated (with a feature flag for
  graceful fallback).
- Same for Lever, Ashby, SmartRecruiters, Workday.
- Keep `Phenom`, `Radancy`, `SuccessFactors`, `Avature`,
  `GenericOfficialHtml`, `GoogleCareersAdapter` indefinitely.

**What doesn't change**:
- DB schema, LLM, dashboard, filters, dedup, lifecycle.

**Risk**: medium. Real-world regressions possible.

**Test of success**:
- After each legacy adapter is deprecated, the corresponding
  declarative spec produces the same output on 100% of the
  legacy adapter's saved fixtures.
- The legacy code is moved to a `legacy_adapters/` directory with
  a deprecation warning at module load time.

---

## Summary: migration timeline (suggested)

| Phase | Effort | Description | Risk |
|---:|---|---|---|
| 0 | done | Audit (this document) | zero |
| 1 | 1-2 days | Bridge runtime output to legacy `HttpFetcher`. Test on 4 PASS sources only. | low |
| 2 | 1-2 days | Lift dedup + lifecycle | low |
| 3 | 2-3 days | Add `DeclarativeSourceAdapter` as a sibling of legacy adapters | medium |
| 4 | 3-5 days | Verify equivalence between Declarative and Legacy where applicable | medium |
| 5 | 1 day | Documentation + process for Hermes-only-on-unresolved | low |
| 6 | 1-2 weeks | v0.2 schema design (with all evidence) | high |
| 7 | 1 day | Dashboard polish | zero |
| 8 | ongoing | Decommission legacy adapters one by one | medium |

Total to a fully merged system: ~4-6 weeks of engineering.

---

## Risks and open questions

1. **Pagination for declarative single-chunk sources**: how does
   the new architecture know `total` for completeness evaluation
   when the response includes everything? Currently: `meta.total`
   for Greenhouse/Eightfold. But the spec doesn't distinguish
   "single chunk with explicit total" from "single chunk with
   total inferred from response length". A `meta.total_path` is
   supported. **Risk: low, but requires care.**

2. **Detail hydration for sources where description is not inline**:
   the legacy `pipeline/detail_enrichment.py` does HTML scraping
   of official job pages. This is a per-source policy (CYBER /
   NEEDS_MORE_DETAIL jobs only). The new architecture needs the
   same policy. **Risk: medium — could be done as a downstream
   detail-enrichment module that wraps the legacy code.**

3. **Rate limiting**: the legacy `HttpFetcher` has pacing,
   circuit breakers, retry-after. The new runtime is render-only.
   Whoever issues the actual HTTP must respect the same pacing.
   **Risk: low — the legacy code already does this.**

4. **AI analysis prompt versioning**: the legacy AI has a prompt
   version. The new declarative extraction does not have any
   "prompt" — it has a spec. The fingerprint for change detection
   should include the spec version. **Risk: low.**

5. **Source health monitoring**: the legacy has
   `consecutive_empty_scans` on the `Portal` table. The new
   architecture has no such concept because it doesn't have a
   `Portal` table. **Risk: medium — need to add a
   `source_health` table or a column on `SourceJob`.**

6. **Telegram notifications**: not investigated in this audit. If
   they exist, they read from the DB and would work unchanged
   with the new pipeline. **Risk: low.**

---

## Integrity statement

- 0 files in `JobResearCHEF/` modified
- 0 files in `runtime/` that are frozen (`spec_executor.py`,
  `source_spec.schema.json`, `job.schema.json`,
  `sources/mercedes.json`, `sources/nvidia.json`) modified
- 0 live HTTP requests issued
- 0 browser calls
- 121 PASS tests still green (42 frozen + 24 batch1 + 29 batch2
  revised + 26 batch3)
