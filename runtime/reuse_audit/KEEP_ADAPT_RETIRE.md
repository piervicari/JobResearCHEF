# KEEP / ADAPT / RETIRE — Component Decision Matrix

> **Audit-only document.** Pure classification. No component is
> modified by this audit. Decision = "keep almost as-is" / "adapt
> then reuse" / "retire because the new model makes it redundant".

Each component has a short justification and a pointer to the
new-runtime analog (if any).

---

## KEEP (10 components)

These are reusable almost as-is in the new architecture. They solve
problems orthogonal to the `source_spec/v0.1` declarative contract.

### K1. DB models (`db/models.py`, `db/migrations.py`, `db/session.py`, `db/backup.py`, `db/recovery.py`)

- **Why keep**: 519 LOC of mature SQLAlchemy ORM modelling 10 tables
  with explicit FK constraints, indexes, and unique constraints.
  The `SourceJob` row model is rich enough to hold both the
  declarative-spec extraction AND the legacy adapter raw payload.
  Backup + integrity-check + recovery drills are already
  implemented and tested.
- **New analog**: `runtime/job.schema.json` is a tiny 16-property
  JSON schema for the normalized output. The DB is downstream of
  the executor; nothing about the spec_executor depends on the
  DB. They are complementary, not overlapping.
- **Recommendation**: USE_OLD. Do not rewrite.

### K2. HTTP safety layer (`pipeline/http.py` + `pipeline/cache.py`)

- **Why keep**: 640 LOC of httpx + per-domain semaphore +
  `min_interval_seconds` + jitter + `max_response_bytes` +
  redirect chain cap + public-DNS validation + private-IP
  rejection + Retry-After honor + access-challenge detection +
  host circuit breaker + file cache with ETag/Last-Modified
  conditional GET. This is **far more mature** than anything in
  `runtime/spec_executor.py` (which has zero HTTP — by design).
- **New analog**: `runtime/spec_executor.py` only renders
  request structures. It does NOT issue HTTP. Any future runtime
  that does issue HTTP MUST reuse this layer.
- **Recommendation**: USE_OLD. The new executor is
  `render-only`; the existing fetcher is `transport-only`. They
  compose cleanly if the executor output becomes the fetcher
  input.

### K3. Normalizer (`pipeline/normalizer.py`)

- **Why keep**: `html.unescape` + selectolax tag stripping +
  NFKC unicode normalization + title canonicalization +
  location canonicalization. This is exactly the function the
  `runtime/spec_executor.py::_strip_html` lacks (it does only
  regex `<[^>]+>` stripping). Cloudflare's HTML-entity-encoded
  `content` field needs `html.unescape` — JobResearCHEF has it
  ready.
- **New analog**: `_strip_html` in `runtime/spec_executor.py`.
- **Recommendation**: USE_OLD. The downstream classifier (after
  the runtime extracts the description) should call the
  existing `html_to_text(value)` for Cloudflare-style payloads
  — same one-line fix that is currently flagged as a downstream
  responsibility in `runtime/candidates/cloudflare.json`.

### K4. Dedup (`pipeline/dedup.py`)

- **Why keep**: `source_identity`, `ats_identity`,
  `canonical_fingerprint` (sha256 over cluster_id + normalized
  title + normalized location + requisition_id), and
  `canonical_application_url` (strip utm_*, strip tracking
  query params, normalize trailing slashes). All test-stable.
- **New analog**: `runtime/spec_executor.py` has zero dedup
  primitive; `source_spec/v0.1` does not declare dedup. The new
  architecture treats dedup as **downstream concern**, not a
  spec responsibility. This is fine — but the implementation
  must come from somewhere.
- **Recommendation**: USE_OLD. Lift `pipeline/dedup.py` as the
  canonical dedup library. No rewrite needed.

### K5. Lifecycle / OPEN/CLOSED (`pipeline/lifecycle.py` + `pipeline/discovery.py`)

- **Why keep**: 550 LOC implementing `process_scan_results`
  (persist observations, compute fingerprint, update canonical
  jobs, dedup, mark `closed_at` via `missing_successful_scans >=
  closure_missed_successful_runs`, with `closure_missed_successful_runs=2`).
  This is the production-grade equivalent of `v0.1`'s
  `closed_decision` + the schema's `authoritative_for_closed` flag.
  More robust because it survives missed runs.
- **New analog**: `runtime/spec_executor.py::closed_decision`.
  The new executor's CLOSED decision is a single boolean per
  run; the legacy lifecycle is a multi-run accumulator. The
  legacy is strictly stronger.
- **Recommendation**: USE_OLD. Keep the legacy lifecycle as the
  authoritative CLOSED driver. The runtime emits
  `AdapterScanResult(is_complete_snapshot=...)` per source per
  run; the legacy code consumes it.

### K6. Source identity (`pipeline/source_identity.py`)

- **Why keep**: Detects provider-ID conflicts (same native ID,
  materially different title/location/apply_url → keep distinct
  variant). 55 LOC. This is exactly what `secondary_id_paths`
  + `canonical_fingerprint` aim to support in `v0.1`.
- **New analog**: `v0.1`'s `secondary_id_paths` + the executor's
  `extract_item` semantics.
- **Recommendation**: USE_OLD. The executor extracts, the
  identity layer decides.

### K7. Source-of-truth adapter base contract (`sources/base.py`)

- **Why keep**: `RawJob` dataclass is a stable, language-neutral
  normalized job interface that maps cleanly to `job.schema.json`
  + the per-ATS adapter outputs. `PortalTarget` is a clean input
  to the adapter. `SourceAdapter` Protocol + `AdapterRegistry`
  is a tested composition root.
- **New analog**: `runtime/job.schema.json`. Same conceptual
  shape; the new schema is just JSON, not Python.
- **Recommendation**: USE_NEW. The new JSON schema is the wire
  format. The legacy `RawJob` is the in-process format. They are
  isomorphic and convert with a one-liner. Do not keep both;
  pick JSON Schema as the source of truth and implement an
  adapter from `job.schema.json` → `RawJob` (or directly to DB).

### K8. ATS adapters (Ashby, Avature, Greenhouse, Lever, Oracle, Phenom, Radancy, SmartRecruiters, SuccessFactors, Workday)

- **Why keep**: Each is a mature, tested adapter (28 tests in
  `tests/test_ats_adapters.py` cover Ashby/Avature/Greenhouse/Lever/Oracle/Phenom/Radancy/SmartRecruiters/SuccessFactors/Workday with real saved fixtures in `tests/fixtures/`). All implement the same `SourceAdapter` protocol. They have explicit pagination, total-count, and "natural_end" detection. They have fixture-backed tests with real saved JSON/HTML responses.
- **New analog**: `runtime/candidates/{microsoft,cloudflare}.json` are v0.1 specs for Greenhouse (Cloudflare) and SmartRecruiters (Microsoft, but via Eightfold). The legacy adapters could be replaced by these specs — but the legacy adapters work TODAY on real responses (per saved fixtures), whereas the new specs are only verified against 1-2 captured responses per source.
- **Recommendation**: MERGE. Use the v0.1 spec format as the **wire** for new sources. Use the legacy adapters as the **runtime** for the 10 ATSes above. Long-term, port each legacy adapter to a v0.1 spec; short-term, do not duplicate work.

### K9. AI / LLM classifier (`ai/job_analyzer.py` + `ai/job_triage.py` + `ai/llm_router.py`)

- **Why keep**: 540 + 386 + 712 = 1638 LOC of mature free-only LLM
  routing, batched analysis, structured-output validation with
  Pydantic, retry-aware fallback (minimax m3 free → m2.7 free →
  gemini flash), JSON-repair before model downgrade, prompt
  versioning. Already validated in `docs/reports/LLM_ROUTING_BENCHMARK_2026-09-02.md`.
- **New analog**: The new architecture has zero LLM code.
- **Recommendation**: USE_OLD. The semantic classifier is the
  primary value-add of the project; the v0.1 spec is only the
  harvesting contract.

### K10. Filters (cyber, geography, seniority)

- **Why keep**: YAML-driven, contextual-term-aware, audited. Cyber
  filter has been benchmarked in
  `docs/reports/taxonomy_benchmark.md`. The new architecture has
  zero filtering code.
- **Recommendation**: USE_OLD. These are downstream of
  `job.schema.json`-shaped normalized output. The
  `spec_executor.py` produces the input the filters expect.

---

## ADAPT (12 components)

These are valuable but must be wrapped, repointed, or adapted to
speak the new v0.1 spec or to live in the new runtime.

### A1. AdapterRegistry (`sources/ats/registry.py` + `sources/base.py`)

- **Why adapt**: The current registry is ordered-by-priority
  (`structured_adapter_registry` vs `default_adapter_registry`)
  and dispatches on `PortalTarget`. It has zero knowledge of
  `source_spec/v0.1` specs. The new architecture wants a registry
  that can dispatch to **either** an existing Python adapter OR
  a `source_spec/v0.1` candidate, depending on what the source
  registry entry says.
- **Adaptation**: introduce a `DeclarativeSourceAdapter` class
  that wraps `spec_executor.py` + a `source_spec/v0.1` JSON file,
  implementing the same `SourceAdapter` Protocol. Then the
  existing `structured_adapter_registry()` can be extended to
  load both Python adapters and declarative specs from
  `runtime/candidates/*.json`.
- **Recommendation**: ADAPT. Wrap, do not rewrite.

### A2. CLI (`cli.py`)

- **Why adapt**: 29 commands including `scan-discover`,
  `triage-pending`, `analyze-pending`, `enrich-details`,
  `ingest-linkedin-csv`, `llm-preflight`. They assume the
  legacy pipeline. If a future v0.2 declarative runtime ships,
  the CLI commands must accept both modes.
- **Adaptation**: keep the legacy CLI working; add new CLI verbs
  (e.g. `research-agent harvest-declarative --spec
  runtime/candidates/cloudflare.json`) that wire
  `spec_executor.py` into the same persistence + lifecycle
  + dedup pipeline. No need to modify the existing commands.
- **Recommendation**: ADAPT. Extend, do not rewrite.

### A3. Scanner (`pipeline/scanner.py`)

- **Why adapt**: 429 LOC orchestrating per-portal fetches with
  isolation, page budgets, per-portal max_jobs. It expects a
  `PortalTarget`. A declarative spec does not have a `PortalTarget`
  — it has a `request.url`. The scanner must learn to consume
  both shapes.
- **Adaptation**: introduce a `HarvestPlan` interface:
  ```python
  class HarvestPlan(Protocol):
      def iter_requests(self) -> Iterable[FetchRequest]: ...
      def consume(self, response: FetchResponse, history: list[dict]) -> Iterable[RawJob]: ...
  ```
  A `DeclarativeHarvestPlan(spec)` wraps a `source_spec/v0.1`.
  The existing `scanner.run()` accepts a list of
  `(PortalTarget | HarvestPlan)` and dispatches.
- **Recommendation**: ADAPT. Extend, do not rewrite.

### A4. Cache (`pipeline/cache.py`)

- **Why adapt**: Currently keyed by URL (sha256). The new
  declarative mode might emit `offset=N` requests with the same
  URL but different page values; the cache key must include the
  offset.
- **Adaptation**: extend `_key(url)` to `_key(url, method,
  body_hash, header_hash)`. The existing conditional-GET logic
  is unchanged.
- **Recommendation**: ADAPT. Small refactor, no rewrite.

### A5. Discovery persistence (`pipeline/discovery.py`)

- **Why adapt**: 318 LOC of "persist observations without making
  semantic job decisions". The new architecture wants the
  same: the runtime emits raw normalized jobs; the discovery
  layer persists them with status `PENDING_AI` and a stable
  payload hash. Currently the discovery layer consumes
  `AdapterScanResult` from a Python adapter; it must also
  consume the equivalent from a declarative run.
- **Adaptation**: add a `DeclarativeScanResult` carrying the
  same fields (`jobs`, `is_complete_snapshot`, `warnings`).
- **Recommendation**: ADAPT. Trivial addition.

### A6. V2 migration (`pipeline/v2_migration.py`)

- **Why adapt**: 143 LOC bridges legacy V1 to V2. If we add a
  v0.2 spec-driven mode, we have to think about V3. But this is
  premature. Just keep V2 migration and avoid breaking it.
- **Recommendation**: KEEP for now; only ADAPT if v0.2 lands.

### A7. Dashboard (`dashboard/app.py` + `dashboard/queries.py`)

- **Why adapt**: The dashboard queries read directly from the
  legacy DB schema. If the runtime writes to the same DB (which
  it should), the dashboard works unmodified. But the dashboard
  has no concept of "which adapter extracted this" beyond the
  legacy `adapter: str` field. Add a `source_spec_version` /
  `extraction_mode` discriminator to the `SourceJob` row so the
  dashboard can show "extracted by declarative spec v0.1" vs
  "extracted by GreenhouseAdapter".
- **Recommendation**: ADAPT. Minor schema addition, no rewrite.

### A8. Payload canonical schema (`pipeline/payload.py`)

- **Why adapt**: `canonical_job_payload` defines a hash-stable
  representation across all sources. The new v0.1 spec emits a
  normalized `Job` dict that should produce an equivalent
  payload_hash. Currently the legacy hash uses legacy field
  names (e.g. `job_description`); the new schema uses `description`.
  These need to be unified.
- **Adaptation**: extend `canonical_job_payload` to accept a
  `source_spec_version` parameter and produce a versioned
  payload hash. The v0.1 payload_hash must be reproducible
  regardless of which adapter extracted the row.
- **Recommendation**: ADAPT. Critical for dedup correctness
  when mixing legacy + declarative runs.

### A9. Adapter common helpers (`sources/ats/common.py`)

- **Why adapt**: `parse_datetime`, `require_list`, `require_mapping`,
  `require_success`, `string_value` are excellent primitives
  that the new executor would benefit from. Currently they are
  Python-only, called inside adapter code.
- **Adaptation**: re-implement the same logic in
  `runtime/spec_executor.py`'s date parser and dotted-path
  getters. Or: keep the helper as a downstream utility called
  by the runtime.
- **Recommendation**: MERGE. Adopt the same semantics
  (especially date parsing) but keep the executor source-agnostic.

### A10. Settings / config (`config.py` + `config/settings.yaml`)

- **Why adapt**: 27 settings keys for scanner (concurrency,
  max_retries, max_response_bytes, gates). Currently the new
  runtime has no settings — `spec_executor.py` is parameterless.
- **Adaptation**: if a future v0.2 declarative runtime becomes
  HTTP-aware, it should pull its pacing from the same YAML.
  Today: keep the new runtime parameterless, but document that
  v0.2 should consume `scanner.*` keys.
- **Recommendation**: ADAPT. Low priority.

### A11. Source health / circuit breakers

- **Why adapt**: The legacy `HttpFetcher` opens per-host
  circuits on access-challenge signals. The new runtime does
  no HTTP. If v0.2 declarative runtime gains HTTP, it must
  inherit this safety.
- **Recommendation**: ADAPT. Critical for safety in v0.2.

### A12. Operator flow scripts (`scripts/run_core_trial.sh`, `scripts/run_p0_core_expansion.sh`, `scripts/run_google_careers_probe.sh`)

- **Why adapt**: They invoke the legacy CLI. If a v0.2
  declarative CLI is added, the scripts must be updated.
- **Adaptation**: add `--harvest-mode declarative|legacy|hybrid`
  to the underlying CLI and forward to the scripts.
- **Recommendation**: ADAPT.

---

## RETIRE (7 components)

These are replaced or made redundant by the new model
`Hermes discovery → SourceSpec → executor → DB → classifier →
dashboard`. The new architecture makes them unneeded.

### R1. Universal source resolver

- **What**: the entire `company/portal_registry.py` +
  `company/registry_changes.py` +
  `company/tier_s_operational_sources.py` infrastructure that
  tries to auto-detect an ATS family from URL/HTML heuristics.
- **Why retire**: the new model says **explicit > inferred**.
  Each `source_spec/v0.1` declares exactly which ATS protocol
  to use. There is no universal resolver because there is no
  universal ATS. The `PortalTarget` shape is replaced by the
  `request.url` + `extraction.stable_id_path` shape.
- **What replaces it**: `Hermes discovery` is a one-time,
  human-curated activity per company (the current `runtime/`
  exercises). The discovered source becomes a `source_spec/v0.1`
  JSON file under `runtime/candidates/`. No inference at runtime.
- **Justification**: the legacy portal resolution wave
  artifacts in `data/portal_resolution/wave5.csv` and
  `wave6.csv` are evidence of the cost of the inference model.
  5.7 MB of CSVs, multiple waves, audit files, registry
  corrections runs 17/23/24/26/27 — that's the iteration cost of
  trying to be universal. The new model says: skip the inference
  loop. Make humans (or the discovery agent) pick the protocol
  explicitly.

### R2. Portal resolution heuristics (`docs/architecture/0002-conservative-url-normalization.md`)

- **What**: 158 LOC of URL normalization + portal_id resolution.
- **Why retire**: same reason as R1. The new model does not need
  portal_id; it has `(company_id, source_platform, source_job_id)`.
- **What replaces it**: URL normalization can live in
  `runtime/candidates/*.json` itself (`apply_url_template`,
  `official_url_template`).

### R3. `master_company_universe` CSVs and portal-resolution waves

- **What**: 5.7 MB CSV with ~thousands of companies + portal
  resolution waves + audit CSVs.
- **Why retire**: the new architecture starts from a known,
  audited set of companies (Mercedes, NVIDIA, Microsoft,
  Amazon, Apple, Google, Meta, Cloudflare). When the next source
  arrives, Hermes discovery produces a single JSON spec. There
  is no need for a 5.7 MB master CSV.
- **What replaces it**: `runtime/candidates/*.json` is the source
  registry.
- **Caveat**: the legacy master CSV is a useful **reference dataset**
  for future Hermes discovery. Keep it as a frozen data asset in
  `data/company_universe/`. Do not use it as a runtime input.

### R4. Generic HTML fallback as primary discovery

- **What**: `GenericOfficialHtmlAdapter` is the last-resort
  adapter when no structured ATS matches.
- **Why retire for new architecture**: the new model says: if
  no `source_spec/v0.1` exists for a source, that source is
  `UNRESOLVED` (see `meta_UNRESOLVED.md`). Generic HTML scraping
  is not a substitute for explicit knowledge of the protocol.
- **What replaces it**: Hermes discovery → `source_spec/v0.1`
  → if the protocol is server-rendered HTML (rare; Phenom is
  one), the spec declares that. If we cannot produce a spec,
  the source stays UNRESOLVED, not "guessed by HTML scraping".
- **Caveat**: the legacy generic adapter is **still useful** as
  the fallback for the 11 ATS adapters when they fail. Do not
  retire it from the legacy runtime.

### R5. Inline portal resolution at scan time

- **What**: `pipeline/scanner.py::load_portal_targets` loads the
  portal registry at scan time and dispatches per-portal.
- **Why retire**: redundant with the explicit `source_spec/v0.1`
  approach. The new runtime does not load any portal registry;
  it loads one source spec at a time.
- **What replaces it**: the new runtime takes a single
  `--spec runtime/candidates/<company>.json` argument per
  harvest. No registry lookup.

### R6. Repeated source resolution heuristics

- **What**: every adapter has its own `supports(target)` method
  (`AshbyAdapter.supports`, `GreenhouseAdapter.supports`, ...)
  that tries to identify a portal via URL/host/path heuristics.
- **Why retire**: redundant with the explicit v0.1 spec model.
  A spec is unambiguous: `request.url` is the request, no
  heuristics needed.
- **What replaces it**: the spec is the spec. No `supports()`
  needed.

### R7. AI batch retries across free providers

- **What**: `ai/llm_router.py` has 712 LOC implementing
  multi-provider fallback for the LLM. The new architecture
  has zero LLM.
- **Why retire for the spec runtime**: the spec runtime is
  pure data extraction, no LLM. LLM is downstream.
- **Caveat**: do not retire the LLM router itself — it is the
  primary value of the project. It is reused unchanged in the
  downstream classifier.

---

## Net result

- **KEEP (10)**: the operational and analysis layers (DB, HTTP,
  dedup, lifecycle, AI, filters) are essentially reusable as-is.
- **ADAPT (12)**: adapter registry, scanner, CLI, cache,
  discovery, dashboard, payload hashing need light wrapping.
- **RETIRE (7)**: the universal source resolver + master CSV +
  portal resolution heuristics are replaced by explicit
  `source_spec/v0.1` declarations.

The new architecture does not need to be a giant rewrite. It
needs to:

1. Wrap the existing 11 ATS adapters in a `SourceAdapter`
   Protocol that the new runtime can dispatch to alongside
   declarative specs.
2. Lift `pipeline/http.py` + `pipeline/cache.py` + `pipeline/normalizer.py`
   + `pipeline/dedup.py` + `pipeline/lifecycle.py` + `ai/*`
   + `db/*` + `dashboard/*` + `filters/*` as-is.
3. Delete `master_company_universe` and the wave resolution
   logic. Use `runtime/candidates/*.json` as the source registry.
4. Add a thin `DeclarativeSourceAdapter` that wraps
   `runtime/spec_executor.py` + a `source_spec/v0.1` JSON.

**No file of `runtime/` needs to change to do this.** This is
purely additive on the JobResearCHEF side, which is the cleanest
outcome of the audit.
