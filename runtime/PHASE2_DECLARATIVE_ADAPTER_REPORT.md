# Phase 2 — DeclarativeSourceAdapter report (JobResearCHEF sibling integration)

**Date:** 2026-09-06
**Mode:** fully offline (zero live HTTP, zero browser, zero new discovery)
**Decision log:** `docs/decisions/0054-declarative-source-adapter-sibling-phase2.md`
(plus §5 safety correction appended to `PHASE1_HTTP_BRIDGE_REPORT.md`)

## Architecture

- `DeclarativeSourceAdapter` file:
  `JobResearCHEF/research_agent_v24/src/research_agent/sources/declarative/adapter.py`
  (one shared class; NVIDIA/Microsoft/Mercedes traverse identical code —
  static token scan enforced, 0 source tokens in `adapter.py`/`bridge.py`/`executor.py`)
- Registry integration: `structured_adapter_registry(declarative_adapters=())`
  — optional parameter, appended after legacy adapters; no-arg call is
  byte-identical to the legacy registry (pinned by name-tuple test)
- Binding mechanism: versioned `sources/declarative/bindings.json`
  (portal URL → spec file); `supports()` is exact string equality only.
  No DB change, no heuristics (5 negative tests: unbound / similar-host /
  same-ATS-family / company-text / duplicates-rejected)
- Packaging: canonical runtime lives in `sources/declarative/`
  (`executor.py`, `bridge.py`, `adapter.py`, `schemas/`, `specs/`,
  `bindings.json`, `README.md`); `runtime/spec_executor.py` and
  `runtime/jobresearchchef_bridge.py` arefilesystem symlinks to the
  canonical modules — one implementation, frozen offline suites keep
  validating it through the links, static text scans stay meaningful
- New persistence layer created: NO (AdapterScanResult → existing
  Scanner → `process_scan_results` → SourceJob/lifecycle unchanged)

## RawJob compatibility

- Source identity format: `declarative:<company_id>` (schema version
  excluded so v0.1→v0.2 never forks jobs); native id in `source_job_id`;
  single secondary id → `ats_job_id`, full list + native item in payload
- Description + qualifications composition: PASS
  (`"\n\nQualifications:\n"` heading iff quals non-empty; empty quals →
  byte-identical description)
- Department preserved in raw_payload: yes
- Organization preserved: yes
- Qualifications preserved separately: yes (+ locations, detail_complete,
  source_platform, secondary ids, `_declarative` provenance, `_source_native`)
- Qualification-only change alters legacy payload hash: PASS (mandatory
  test: description differs AND `serialize_observation_payload` sha differs)

## Catalog (all MockTransport, real HttpFetcher)

- Mercedes catalog: PASS (real frozen item: POST, `SearchCriteria=[]`,
  1 job + terminal probe = 2 requests, complete snapshot true,
  responsibilities + qualifications in semantic text)
- NVIDIA catalog: PASS (25 synthetic jobs, 3 catalog pages, complete true)
- Microsoft catalog: PASS (12 jobs, 2 pages, complete true, same adapter
  instance as NVIDIA — shared execution path demonstrated)
- NVIDIA detail requests during catalog scan: 0
- Microsoft detail requests during catalog scan: 0
  (`render_detail_fetch` helper exists but `scan()` never calls it)

## Completeness

- Mercedes / NVIDIA / Microsoft complete-snapshot logic: PASS
- Incomplete/page-cap scan → complete_snapshot=false: PASS (+ warning)
- Job-cap truncation → complete_snapshot=false: PASS (+ warning)
- Empty-before-total → complete_snapshot=false: PASS (jobs kept, warning, no close)
- Changing total → complete_snapshot=false: PASS (+ warning)
- v0.1 off-by-one bug status: FIXED (generic BUGFIX in canonical
  `evaluate_completeness`: boundary arithmetic now shared with
  `pagination_iterator`, incl. the `max(0, …)` guard for total==first;
  probe placement fixed in the same case. NOT a v0.2 feature. Regression:
  `test_boundary_total_needs_no_phantom_data_page`,
  `test_single_item_catalog_needs_data_page_plus_probe`,
  iterator/evaluator agreement sweep. All 42 frozen runtime tests pass
  unchanged through the symlink.)

## Registry

- Unbound portal selected by declarative adapter: NO
- Heuristic matching introduced: NO
- Legacy registry behavior unchanged: yes (name tuple pinned; full legacy
  adapter/scanner/lifecycle suites green)

## Networking

- New HTTP client: NO; duplicated retries/pacing/circuit-breaker/cache: NO
- 403 → `require_success` → `AdapterHttpError` (standard path, tested)
- 429 → immediate `HostCircuitOpenError`, never retried (report corrected,
  tested with single-call assertion)
- Live HTTP requests: 0; browser calls: 0

## Legacy finding (§28)

- AI requeue on payload_changed: LEGACY_BUG_CONFIRMED
- Evidence: `_update_source_job` (`pipeline/lifecycle.py`, ~lines 496–524)
  persists every raw field + `payload_sha256` but never touches `ai_status`;
  pinned by `test_ai_status_not_requeued_by_lifecycle_on_payload_change`
  (quals-only change → `payload_changed=True` while `ai_status` stays
  `CYBER`). Requeue-on-change exists only in the separate
  `discovery.persist_scan_discoveries` path (`if content_changed`), which
  is not the `scan_portals` + `process_scan_results` path. Not fixed in
  Phase 2 per plan; required input for future LLM-on-change work.

## Tests

- Old runtime tests: 42 + 24 + 29 + 26 = 121 PASS (through symlinks)
- Bridge tests: 22 PASS (venv, real Fetcher) / 19 + 3 skip (system python)
- JobResearCHEF regression: 294 PASS (full `tests/`, incl. HTTP, scanner,
  ATS adapters, lifecycle, payload, AI, dashboard)
- New declarative adapter tests: 31 PASS (binding×7, Mercedes×2,
  NVIDIA/Microsoft×3, converter/hash×5, completeness×6, static×1,
  off-by-one×3, bridge-merge×1, lifecycle×3)
- Total: 121 + 22 + 294 (31 new incl.) — 0 fail

## Files

- Frozen schema capability changes: 0 (`strategy` still `const: offset`;
  no v0.2 primitives; no migrations)
- New DB migrations: 0; RawJob/SourceJob/CanonicalJob unchanged
- New source-specific branches: 0
- Tracked modifications in JobResearCHEF: 1 file (`sources/ats/registry.py`,
  +15/−2, optional parameter only); everything else is new files
- `runtime/` tracked edits: Cloudflare archival + NEEDS_EXTENSION doc (pre-flight),
  Phase-1 safety correction, 2 file→symlink swaps, 2 new reports; no frozen
  behavior duplicated
