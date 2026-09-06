# 0054 — DeclarativeSourceAdapter as a registry sibling (Phase 2)

**Status:** Accepted / Phase 2 (offline proof-of-integration, no live traffic)
**Date:** 2026-09-06
**Supersedes packaging note of:** 0053 (bridge placement now canonical)

## Decisions

1. **DeclarativeSourceAdapter is a sibling of the legacy SourceAdapters.**
   One shared class (`research_agent/sources/declarative/adapter.py`)
   implements the existing `SourceAdapter` Protocol
   (`supports` / `scan` → `AdapterScanResult`). Legacy adapters are
   untouched. `structured_adapter_registry()` gains an optional
   `declarative_adapters=()` parameter (appended after legacy
   adapters); called without arguments the registry and its order are
   byte-identical to before.

2. **SourceSpec selection is explicit binding, never heuristic
   inference.** `supports()` is plain string equality between
   `PortalTarget.normalized_jobs_url` and the keys of the versioned
   `sources/declarative/bindings.json`. No host similarity, no
   ATS-family check, no substring/regex. Notably the spec's own
   `request.url` (API endpoint) is never compared to the portal URL.
   Negative tests pin that similar hostnames, matching ATS families
   and matching company text do NOT select the adapter.

3. **Catalog scan does not N+1 hydrate separate detail endpoints.**
   `scan()` only walks catalog pages. Specs with
   `description_in_catalog=false` yield jobs with empty descriptions
   and `detail_complete=false` in the payload; detail hydration for
   new/changed/candidate jobs is a later phase. A standalone
   `render_detail_fetch()` helper exists for explicit one-off use and
   is never called by `scan()` (counter-asserted: catalog jobs = N,
   network calls = catalog pages only).

4. **Qualifications are composed into legacy RawJob.description during
   the compatibility phase while preserved structurally in
   raw_payload.** Composition is deterministic
   (`description + "\n\nQualifications:\n" + qualifications`, heading
   only when non-empty), source-agnostic, and hash-visible: the legacy
   observation hash covers the composed text, so a qualifications-only
   change alters it (mandatory test). No DB migration in Phase 2: no
   new columns on RawJob/SourceJob/CanonicalJob, no new persistence
   layer, no new lifecycle — `AdapterScanResult` flows into the
   existing Scanner → `process_scan_results` path unchanged.

5. **Existing Scanner/HttpFetcher/lifecycle remain single owners of
   safety/persistence/closure.** The adapter reuses `require_success`
   (non-2xx → `AdapterHttpError`, no custom retry/recovery), honors
   `context.page_limit` / `max_jobs_per_portal` (truncation forces
   `is_complete_snapshot=false` + warning), and computes
   `is_complete_snapshot` only when `evaluate_completeness` passes AND
   the spec is authoritative AND no cap/anomaly/total-change occurred —
   which is exactly what the legacy close-jobs logic requires.

6. **Source identity for declarative jobs is namespaced by company and
   stable across SourceSpec schema upgrades.**
   `RawJob.source = "declarative:<company_id>"` (schema version
   excluded on purpose); native stable id stays in `source_job_id`;
   secondary ids preserved in payload (+ `ats_job_id` when
   unambiguous).

## Why

Phase 1 proved the request path (spec → bridge → FetchRequest). Phase 2
closes the loop to persisted jobs without forking the pipeline: one
adapter class, one bindings file, zero heuristic resolution, zero new
infrastructure. The three active PASS specs (Mercedes, NVIDIA,
Microsoft) traverse identical code (static token scan enforced).

## Implementation shape

```text
sources/declarative/
  executor.py   (canonical v0.1 executor + generic boundary BUGFIX)
  bridge.py     (urllib.parse query merge; FetchRequest only)
  adapter.py    (bindings, identity, converter, offset scan loop)
  schemas/      (v0.1 schemas)  specs/  (3 PASS specs)
  bindings.json (portal URL -> spec, exact match)
runtime/spec_executor.py + runtime/jobresearchchef_bridge.py
  are symlinks to executor.py / bridge.py: one implementation,
  frozen offline suites keep validating it.
```

## Trade-offs / challenges

- The v0.1 `evaluate_completeness` off-by-one (extra data page
  demanded when total lands on a page boundary; probe misplaced in the
  same case; single-item catalogs broken) is fixed generically in the
  canonical executor with a BUGFIX comment + regression tests. The fix
  also corrects `pagination_iterator` agreement; all 42 frozen runtime
  tests still pass unchanged through the symlink.
- `HttpFetcher` 429 semantics corrected in docs (immediate
  `HostCircuitOpenError`, never retried) — behavior unchanged, Phase-1
  report amended.
- Known coexistence quirk: `AdapterScanResult.adapter` name for all
  declarative jobs is the shared `"declarative"` string; per-company
  distinction lives in `RawJob.source` / payload (stable for hashing).
- `source_last_seen_at` travels inside `raw_payload` (stored, NOT
  hashed — the canonical hash covers only application fields), so no
  volatile timestamps can create false content changes.

## Current implementation impact

- New: `sources/declarative/` (executor, bridge, adapter, schemas,
  specs, bindings.json, README) + `tests/test_declarative_adapter.py`
  (31 tests, all offline via MockTransport + temp SQLite).
- Changed: `sources/ats/registry.py` (optional parameter only);
  `runtime/` gains two symlinks (files, not copies).
- Unchanged: all legacy adapters, Scanner, HttpFetcher, lifecycle,
  DB schema (zero migrations), RawJob/SourceJob shapes.

## Open questions

- Phase 3: persist `source_spec_ref` on Portal (bindings currently
  file-based; DB untouched by design in this phase).
- Phase 3: detail-enrichment wiring for new/changed/candidate jobs
  only (policy proven here: catalog scans stay cheap).
- v0.2: `single_request` paging (Cloudflare evidence stands).
- LEGACY_BUG_CONFIRMED (not fixed here): `process_scan_results` /
  `_update_source_job` never reset `ai_status` to PENDING_AI on
  payload change (only `discovery.persist_scan_discoveries` requeues);
  pinned by test, required for future LLM-on-change work.

## Legacy finding (§28)

`AI requeue on payload_changed: LEGACY_BUG_CONFIRMED`. Evidence:
`pipeline/lifecycle.py::_update_source_job` (lines ~496-524) writes
every raw field plus `payload_sha256` but never touches `ai_status`;
`tests/test_declarative_adapter.py::test_ai_status_not_requeued_by_lifecycle_on_payload_change`
shows a qualifications-only change producing
`JobObservation.payload_changed=True` while `ai_status` stays `CYBER`.
The requeue-on-change behavior exists ONLY in the separate
`pipeline/discovery.py::persist_scan_discoveries`
(`if content_changed: source.ai_status = "PENDING_AI"`), which is not
the path `scan_portals` + `process_scan_results` uses. Intentional in
neither direction — discovery.py demonstrates the intended semantic,
lifecycle.py omits it. Not corrected in Phase 2 per plan.
