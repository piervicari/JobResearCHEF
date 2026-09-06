# Declarative sources (`source_spec/v0.1` runtime)

Canonical home of the declarative runtime (Phase 2). Single source of
truth for: the v0.1 executor, the FetchRequest bridge, the sibling
adapter, the v0.1 schemas, the three active PASS specs, and the
explicit portal bindings. `runtime/spec_executor.py` and
`runtime/jobresearchchef_bridge.py` (the offline experiment directory)
are symlinks to `executor.py` / `bridge.py` here, so the frozen
offline suites keep validating this exact implementation.

## Layout

- `executor.py` — source-agnostic v0.1 executor (render / paginate /
  extract / normalize / completeness). Includes one generic BUGFIX to
  `evaluate_completeness` (boundary arithmetic shared with
  `pagination_iterator`; NOT a v0.2 feature — see §24 in the Phase-2
  plan and `test_single_item_catalog_needs_data_page_plus_probe`).
- `bridge.py` — rendered request dict → `FetchRequest` (stdlib
  `urllib.parse` only; never produces `form_body`).
- `adapter.py` — `DeclarativeSourceAdapter` (+ explicit bindings,
  identity rule, normalized→RawJob converter).
- `schemas/` — `source_spec.schema.json`, `job.schema.json` (v0.1).
- `specs/` — `mercedes.json`, `nvidia.json`, `microsoft.json`.
- `bindings.json` — versioned explicit bindings (portal URL → spec).

## Source identity rule

`RawJob.source = "declarative:<company_id>"` (e.g.
`declarative:mercedes-benz`). Rationale:

- Two bound specs may share a platform (NVIDIA and Microsoft are both
  Eightfold-family) and ATS ids are not globally unique across
  companies, so the platform name alone is not a safe namespace.
- The SourceSpec schema version is deliberately EXCLUDED: upgrading a
  company's spec v0.1 → v0.2 must not fork its jobs into new SourceJob
  rows (the dedup key is `(source, source_job_id)`).
- The native stable id is preserved unchanged in
  `RawJob.source_job_id`; the secondary-id list is preserved in
  `raw_payload`, and the single secondary id (when unambiguous) is
  surfaced as `RawJob.ats_job_id`.

## Semantic-text rule (compatibility phase, no DB migration)

Legacy `RawJob.description` = `description`, plus
`"\n\nQualifications:\n" + qualifications` when qualifications are
non-empty. `raw_payload` always keeps `description`, `qualifications`,
`department`, `organization`, `locations`, `detail_complete`,
`source_platform`, `source_secondary_ids` as separate fields, plus
`_declarative` provenance and the `_source_native` catalog item. The
legacy observation hash covers the composed description, so a
qualifications-only change alters the hash (tested).

## Scan policy (enforced, tested)

- Offset pagination only; JobResearCHEF page/job caps always win and
  force `is_complete_snapshot=false` with a warning (never bypassed
  for completeness).
- `is_complete_snapshot` is true only when `evaluate_completeness`
  passes AND the spec is authoritative AND no cap/anomaly/total-change occurred —
  which is exactly what the legacy close-jobs logic requires.
- Terminal probe rule: specs whose completeness rules REQUIRE the
  empty-after-total page always get exactly one terminal probe; specs
  whose rules merely ACCEPT it (`last_page_shorter_than_page_size`)
  get one ONLY when the last data page came back full. A partial final
  page stops the scan with no extra request.
- INVARIANT: catalog traversal completeness != downstream unique-job
  count. History records traversed upstream ITEMS per page; the adapter
  never dedups by stable id. Any future language/variant dedup must
  happen downstream of this accounting (tested).
- Detail endpoints are never fetched during `scan()` (no N+1);
  `render_detail_fetch()` is an explicit one-off helper.
- Non-2xx responses use the standard ATS failure path
  (`require_success` → `AdapterHttpError`); 429 opens the fetcher host
  circuit immediately without retry. No custom recovery here.

## Safety preflight (fail closed)

`scan()` deliberately does not read `spec["safety"]` — network safety
is owned solely by `HttpFetcher`/`Scanner`. Before any live run, the
pure function `safety.preflight_safety(spec, effective)` (also exposed
as `adapter.preflight(target, effective)`) compares spec requirements
against the effective scanner configuration:

- SAFE_TO_RUN / UNSUPPORTED_SAFETY_REQUIREMENT / SCANNER_SETTINGS_TOO_PERMISSIVE.
- `long_pause_*` and `max_consecutive_errors` are NOT_CURRENTLY_SUPPORTED:
  active values fail the preflight honestly instead of being ignored.
- There is no bypass flag; `assert_safe_to_run` raises `UnsafeToRunError`.

## Language status

`preferred_language_codes` is DECLARED_BUT_UNEXERCISED: declared in
the v0.1 schema and the Mercedes spec, read by no runtime code, with
zero fixture evidence (347 real Mercedes items inspected across three
artifacts: only
`PublicationLanguage` Code 1, zero duplicate PositionIDs). No
cross-language dedup engine exists on purpose; see the Mercedes spec
notes for the evidence reference.
