# JobResearCHEF Reuse Audit

> **Audit type**: OFFLINE architectural comparison
> **Date**: 2026-09-05
> **Scope**: what from JobResearCHEF (the legacy project at
> `JobResearCHEF/research_agent_v24`) can be reused by the new
> `runtime/` experiment (declarative `source_spec/v0.1` +
> `spec_executor.py`).
> **Constraint**: zero HTTP traffic. zero browser. zero live
> source discovery. zero commit. zero modification to either
> project. Pure reading + analysis.

---

## 0. Project recap

### JobResearCHEF — the legacy

- Path: `JobResearCHEF/research_agent_v24/`
- Python 3.12+ / `uv` / SQLAlchemy / httpx / selectolax / Streamlit
- ~9,264 LOC of `src/` code; ~32 test modules; ~17 fixture files
- 11 ATS adapters (Ashby, Avature, Greenhouse, Google Careers, Lever, Oracle, Phenom, Radancy, SmartRecruiters, SuccessFactors, Workday) + GenericOfficialHtml fallback + LinkedIn CSV importer
- ~40+ ADRs in `docs/decisions/`, 13 architecture docs, 50+ historical reports
- Persistent runtime DB at `~/.local/share/research-agent/research_agent.db`
- Streamlit dashboard at `http://127.0.0.1:8501`
- Free-only LLM routing (minimax m3 free, gemini flash, etc.)
- Conservative network policy: global_concurrency=8,
  per_domain_concurrency=1, min_interval=1.0s, max_retries=2,
  max_response_bytes=20MB, no rotating proxies, no CAPTCHA
  bypass, no browser
- Status per README: `V2.6` (post-cleanup)

### `runtime/` — the new experiment

- `runtime/source_spec.schema.json` — v0.1 JSON Schema contract (frozen)
- `runtime/spec_executor.py` — generic source-agnostic Python runtime
- `runtime/job.schema.json` — normalized job output schema
- `runtime/sources/{mercedes,nvidia}.json` — frozen PASS_V01 specs
- `runtime/candidates/{microsoft,cloudflare}.json` — PASS_V01 specs
- `runtime/candidates/{amazon,apple,google,meta}_NEEDS_EXTENSION.md` or `.UNRESOLVED.md` — extension pressure records
- 42 frozen regression tests + 24 batch1 + 29 batch2 revised + 26 batch3 = **121 tests** total
- `runtime/EXTENSION_PRESSURE_REGISTRY.md` — cumulative registry of v0.2 candidate capabilities

---

## 1. Component inventory

The inventory below lists every meaningful component present in
JobResearCHEF, with the primary file path and a one-line description.

### 1.1 Source registry & ATS adapters

| Component | Primary file(s) | LOC | Status |
|---|---|---:|---|
| Adapter interface (`SourceAdapter`, `PortalTarget`, `RawJob`, `AdapterScanResult`, `PortalScanContext`) | `src/research_agent/sources/base.py` | 96 | Mature |
| Adapter registry (ordered list + `select(target)`) | `src/research_agent/sources/ats/registry.py` | 52 | Mature |
| GenericOfficialHtml fallback (JSON-LD + anchor extraction, robots.txt) | `src/research_agent/sources/official/generic.py` | 248 | Mature |
| Ashby adapter (single chunk, content=true) | `src/research_agent/sources/ats/ashby.py` | 97 | Mature |
| Avature adapter (HTML pagination, known hosts whitelist) | `src/research_agent/sources/ats/avature.py` | 183 | Mature |
| Greenhouse adapter (boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true) | `src/research_agent/sources/ats/greenhouse.py` | 104 | Mature |
| **Google Careers adapter (Boq batchexecute, positional contract)** | `src/research_agent/sources/ats/google_careers.py` | 287 | Mature code, **historic evidence only** |
| Lever adapter (offset-based skip pagination) | `src/research_agent/sources/ats/lever.py` | 121 | Mature |
| Oracle Recruiting Cloud adapter (HTML bootstrap + JSON API) | `src/research_agent/sources/ats/oracle.py` | 204 | Mature |
| Phenom adapter (Phenom Career Connect, HTML embedded JSON) | `src/research_agent/sources/ats/phenom.py` | 294 | Mature |
| Radancy/Talentbrew adapter (verified hosts whitelist) | `src/research_agent/sources/ats/radancy.py` | 191 | Mature |
| SmartRecruiters adapter (offset pagination) | `src/research_agent/sources/ats/smartrecruiters.py` | 142 | Mature |
| SuccessFactors Recruiting Marketing adapter (HTML pagination) | `src/research_agent/sources/ats/successfactors.py` | 189 | Mature |
| Workday adapter (HTML bootstrap → tenant/siteId → POST JSON) | `src/research_agent/sources/ats/workday.py` | 167 | Mature |
| LinkedIn CSV importer (no scraping) | `src/research_agent/sources/linkedin/importer.py` | 210 | Mature |
| Adapter common helpers (parse_datetime, require_list, etc.) | `src/research_agent/sources/ats/common.py` | 57 | Mature |

### 1.2 HTTP/network layer

| Component | Primary file(s) | LOC | Status |
|---|---|---:|---|
| HTTP fetcher (httpx + rate limiting + retries + redirects + DNS validation + body budget + cache integration) | `src/research_agent/pipeline/http.py` | 640 | Mature |
| File response cache (gzip + etag/last-modified + conditional GET) | `src/research_agent/pipeline/cache.py` | 105 | Mature |
| DomainRateLimiter (per-host semaphore + min_interval + jitter) | inline in `http.py` | n/a | Mature |
| Per-host circuit breaker (open after access-control signal) | inline in `http.py` | n/a | Mature |
| Host circuit open + Retry-After honor | inline in `http.py` | n/a | Mature |

### 1.3 Database & data layer

| Component | Primary file(s) | LOC | Status |
|---|---|---:|---|
| ORM models (10 tables: ImportBatch, CorporateCluster, CompanyAlias, CompanyRecord, Portal, ClusterPortalMapping, RegistryChangeAudit, ScanRun, PortalScanAttempt, CanonicalJob, SourceJob, JobAiAnalysis, JobObservation) | `src/research_agent/db/models.py` | 519 | Mature |
| Schema migration (SQLite additive columns) | `src/research_agent/db/migrations.py` | 82 | Mature |
| DB session/engine factory | `src/research_agent/db/session.py` | 45 | Mature |
| SQLite backup + integrity check | `src/research_agent/db/backup.py` | 177 | Mature |
| Non-destructive restore verification | `src/research_agent/db/recovery.py` | 103 | Mature |

### 1.4 Pipeline

| Component | Primary file(s) | LOC | Status |
|---|---|---:|---|
| Scanner (failure-isolated orchestration over portal registry) | `src/research_agent/pipeline/scanner.py` | 429 | Mature |
| Source identity (handle provider-ID conflicts safely) | `src/research_agent/pipeline/source_identity.py` | 55 | Mature |
| Detail enrichment (second-stage same-host job page fetch for CYBER/NEEDS_MORE_DETAIL) | `src/research_agent/pipeline/detail_enrichment.py` | 541 | Mature |
| Discovery (persist observations without semantic decisions) | `src/research_agent/pipeline/discovery.py` | 318 | Mature |
| Dedup (canonical fingerprint, source identity, application URL normalization) | `src/research_agent/pipeline/dedup.py` | 168 | Mature |
| Lifecycle (persist observations, dedup canonical jobs, update safe state, closure via missed-successful-runs) | `src/research_agent/pipeline/lifecycle.py` | 550 | Mature |
| Normalizer (HTML-to-text, NFKC, title/location canonicalization) | `src/research_agent/pipeline/normalizer.py` | 61 | Mature |
| Filter (cyber + seniority + geography) | `src/research_agent/pipeline/filter.py` | 70 | Mature |
| Gates (post-fetch gate: failure/retry/429/empty thresholds) | `src/research_agent/pipeline/gates.py` | 64 | Mature |
| Payload (canonical observation schema for stable hashing) | `src/research_agent/pipeline/payload.py` | 95 | Mature |
| V2 migration (legacy V1 → V2 schema bridge) | `src/research_agent/pipeline/v2_migration.py` | 143 | Mature |
| Pilot runner | `src/research_agent/pipeline/pilot.py` | 96 | Mature |

### 1.5 AI / semantic

| Component | Primary file(s) | LOC | Status |
|---|---|---:|---|
| Job analyzer (structured batch provider contract) | `src/research_agent/ai/job_analyzer.py` | 540 | Mature |
| Job triage (high-recall pre-filter) | `src/research_agent/ai/job_triage.py` | 386 | Mature |
| LLM router (provider-agnostic + retry-aware + free-only) | `src/research_agent/ai/llm_router.py` | 712 | Mature |
| AI schema (Pydantic) | `src/research_agent/ai/schema.py` | 40 | Mature |

### 1.6 Company / portal registry / filters

| Component | Primary file(s) | LOC | Status |
|---|---|---:|---|
| Corporate cluster resolver | `src/research_agent/company/clustering.py` | n/a | Mature |
| Alias importer + proposer | `src/research_agent/company/aliases.py` | n/a | Mature |
| Company master CSV importer | `src/research_agent/company/importer.py` | n/a | Mature |
| Portal registry builder | `src/research_agent/company/portal_registry.py` | 158 | Mature |
| Registry change audit | `src/research_agent/company/registry_changes.py` | n/a | Mature |
| Tier-S operational source selector | `src/research_agent/company/tier_s_operational_sources.py` | n/a | Mature |
| Cyber filter (yaml-driven, contextual terms) | `src/research_agent/filters/cyber.py` + `config/cyber_keywords.yaml` | n/a | Mature |
| Geography filter | `src/research_agent/filters/geography.py` + `config/geographies.yaml` | n/a | Mature |
| Seniority filter | `src/research_agent/filters/seniority.py` + `config/seniority.yaml` | n/a | Mature |
| Common filter helpers | `src/research_agent/filters/common.py` | n/a | Mature |

### 1.7 Dashboard & observability

| Component | Primary file(s) | LOC | Status |
|---|---|---:|---|
| Streamlit dashboard app | `src/research_agent/dashboard/app.py` | 440 | Mature |
| Dashboard queries (co/portal/source-job/AI views) | `src/research_agent/dashboard/queries.py` | 792 | Mature |
| Structured logging | `src/research_agent/logging.py` | n/a | Mature |

### 1.8 CLI / scheduler

| Component | Primary file(s) | LOC | Status |
|---|---|---:|---|
| Typer CLI (29 commands: scan-discover, triage-pending, analyze-pending, enrich-details, ingest-linkedin-csv, llm-preflight, etc.) | `src/research_agent/cli.py` | n/a (≥1390) | Mature |
| Settings loader (yaml) | `src/research_agent/config.py` | n/a | Mature |
| Secrets management | `src/research_agent/secrets.py` | n/a | Mature |
| Bootstrap scripts (DB, dashboard) | `scripts/bootstrap_*.sh`, `scripts/ensure_dashboard.sh`, `scripts/run_core_trial.sh` | n/a | Mature |

### 1.9 Tests, fixtures, docs

| Component | Primary file(s) | LOC | Status |
|---|---|---:|---|
| 32 test modules (pytest) | `tests/test_*.py` | n/a | Mature |
| Fixture directory (17 files: ashby/avature/greenhouse/lever/oracle/phenom/radancy/smartrecruiters/successfactors/workday JSON+HTML) | `tests/fixtures/` | n/a | Mature |
| ADR log (40+ records) | `docs/decisions/*.md` | n/a | Mature |
| Architecture docs (13 records) | `docs/architecture/*.md` | n/a | Mature |
| Operational reports (~50) | `docs/reports/*.md`, `output/test_runs/*.log` | n/a | Historical |
| CODEX handover (technical state) | `CODEX_HANDOVER_CURRENT.md` | n/a | Mature |

### 1.10 Master & portal resolution

| Component | Primary file(s) | Status |
|---|---|---|
| Master company universe CSV (wave5 → wave6) | `master_company_universe_v1_5_portal_resolution_wave5.csv` (~5.7 MB), `..._v1_6_*.csv` etc. | Mature data |
| Portal resolution waves + audit | `portal_resolution_wave5.csv`, `portal_resolution_wave6.csv`, `..._audit.csv`, `..._summary.json` | Mature data |
| Target employers YAML/CSV | `data/target_employers/*.yaml`, `*.csv` | Mature data |

---

## 2. KEEP / ADAPT / RETIRE matrix

See companion file: `KEEP_ADAPT_RETIRE.md`.

---

## 3. Adapter inventory

See companion file: `ADAPTER_CAPABILITY_MATRIX.md`.

---

## 4. SourceSpec gap analysis

See companion file: `SOURCE_SPEC_GAP_ANALYSIS.md`.

---

## 5. Google adapter audit

See companion file: `GOOGLE_ADAPTER_AUDIT.md`.

---

## 6. Source Status Matrix (corrected post-reuse-audit)

This is the **authoritative** state of source representations as of
this audit (2026-09-05). The classification is:

- **FROZEN_PASS_SPEC**: a source spec living in `runtime/sources/`
  (the frozen dir from v0.1 freeze).
- **ACTIVE_PASS_CANDIDATE**: a source spec living in
  `runtime/candidates/` that is currently valid PASS_V01.
- **REVOKED / ARCHIVED**: a previously PASS spec moved to
  `runtime/candidates/_archive/` with suffix
  `.PASS_V01_then_revoked` (Amazon only).
- **NEEDS_EXTENSION**: no candidate JSON; a `.NEEDS_EXTENSION.md`
  document in `runtime/candidates/` explains the gap.
- **UNRESOLVED**: no candidate JSON; a `.UNRESOLVED.md` document in
  `runtime/candidates/` explains the protocol unknown.

| Source | Current mode | Evidence quality | Declarative v0.1 | Legacy adapter | Recommended runtime path |
|---|---|---|---|---|---|
| Mercedes-Benz | **FROZEN_PASS_SPEC** (`sources/mercedes.json`) | LIVE_FIXTURE (`fixtures/mercedes_catalog_page.json`, real captured) | yes | no | **DECLARATIVE** |
| NVIDIA | **FROZEN_PASS_SPEC** (`sources/nvidia.json`) | LIVE_FIXTURE (`fixtures/nvidia_catalog_page.json` + `fixtures/nvidia_detail.json`) | yes | no | **DECLARATIVE** |
| Microsoft | **ACTIVE_PASS_CANDIDATE** (`candidates/microsoft.json`) | LIVE_FIXTURE (`fixtures/microsoft_catalog_page.json` + `fixtures/microsoft_detail.json`) | yes | no (Microsoft is on Eightfold, but no legacy Microsoft/Eightfold adapter exists in JobResearCHEF) | **DECLARATIVE** |
| Cloudflare | **ACTIVE_PASS_CANDIDATE** (`candidates/cloudflare.json`) | LIVE_FIXTURE (`fixtures/cloudflare_catalog_page.json` + `fixtures/cloudflare_detail.json`) | yes | no (Cloudflare runs on Greenhouse, but no legacy Cloudflare/Greenhouse adapter is wired into the JobResearCHEF master universe) | **DECLARATIVE** |
| Amazon | **REVOKED / ARCHIVED** (`_archive/amazon.json.PASS_V01_then_revoked`) + `candidates/amazon_NEEDS_EXTENSION.md` | LIVE_FIXTURE (`fixtures/amazon_catalog_page.json` + `page2.json` + `empty.json`) — but extraction loses `basic_qualifications` + `preferred_qualifications`; traversal budget insufficient under safety defaults | partial (semantic_complete=false, traversal_complete=false) | no | **HOLD_UNRESOLVED** (cannot promote to declarative until the two extension pressures — multi-field text composition + per-spec traversal budget — are implemented in v0.2) |
| Apple | **NEEDS_EXTENSION** (`candidates/apple_NEEDS_EXTENSION.md`) | LIVE_FIXTURE (`fixtures/apple_catalog_page.json`) for the search endpoint only; no detail endpoint | no | no | **HOLD_UNRESOLVED** (page_number pagination + bootstrap_request + session cookie persistence are required; not in v0.1) |
| Google | **NEEDS_EXTENSION** (`candidates/google_NEEDS_EXTENSION.md`) | NONE — no real fixture saved; the only attempt was batch2 probe (4xx / error GraphQL); legacy `GoogleCareersAdapter` is **CODE_ONLY** (MockTransport tests, no real saved response in `tests/fixtures/`, no log in `output/test_runs/`). The legacy adapter uses the SAME Comet/batchexecute RPC as Meta, but with a STALE persisted-query ID (`r06xKb` from 2026-09-02 ADRs was already failing on 2026-09-05). | no | yes (code-only) | **HOLD_UNRESOLVED** (Google-specific Boq/batchexecute protocol with persisted-query IDs that rotate at every Boq release — requires live doc_id discovery at runtime, which is not in v0.1) |
| Meta | **UNRESOLVED** (`candidates/meta_UNRESOLVED.md`) | NONE — only an error GraphQL response captured; persisted-query ID unknown | no | no (no legacy Meta adapter exists in JobResearCHEF) | **HOLD_UNRESOLVED** (Comet/batchexecute protocol with unknown doc_id; requires bundle JS scraping or browser to obtain) |

### Notes on the matrix

- **Amazon** was REVOKED because, although the v0.1 wire is
  representable, `basic_qualifications` and `preferred_qualifications`
  are dropped (semantic_complete=false) and the safety budget
  cannot traverse the 10000-hit hard cap (traversal_complete=false).
  The legacy code preserved the spec for reference only.
- **Google** is **NEEDS_EXTENSION** but with weaker evidence than
  Apple or Amazon: only CODE_ONLY evidence from the legacy
  adapter (no real Google API fixture in any cache directory).
  The legacy adapter itself is the only artifact, and its
  persisted-query ID is stale.
- **Meta** is **UNRESOLVED** (not NEEDS_EXTENSION) because there
  is no real response payload to evaluate what v0.1 is missing
  (per the rule: NEEDS_EXTENSION requires a successful response to
  demonstrate the gap).
- **Apple** has the strongest evidence of the three unresolved:
  a real `search_results` fixture was captured, confirming
  page_number pagination + JSON body + CSRF bootstrap. But the
  content_type is **`application/json`**, NOT
  `application/x-www-form-urlencoded` (correction from previous
  audit). So Apple is NOT evidence for `form-encoded body`.

---

## 7. Incoherences found in the original reuse audit

The original reuse audit produced before this correction pass
contained three factual errors that this document corrects.

### 7.1 Apple as evidence for `POST form-encoded body`

**Original claim**: "Apple's CSRF bootstrap uses POST form. Same
Comet pattern."

**Reality**: Apple's `/api/v1/search` uses
`Content-Type: application/json` with a JSON body
(`{"query":"", "filters":{...}, "page":N, ...}`). Documented in
`runtime/candidates/apple_NEEDS_EXTENSION.md` line "POST
.../api/v1/search con CSRF token + cookies + JSON body". The
fixture (`fixtures/apple_catalog_page.json`) confirms JSON.

**Correction**: Apple is **not** evidence for the
`POST form-encoded body` capability. Only Google Careers
(`application/x-www-form-urlencoded;charset=UTF-8`) and Meta
Careers (`application/x-www-form-urlencoded`) are.

### 7.2 Google Boq and Meta Comet collapsed into one capability

**Original claim**: "Both Google and Meta use the same Comet
batchexecute RPC."

**Reality**: Both use `POST /<path>/_/.../data/batchexecute` with
form-encoded body and the same envelope. The SHAPE is similar.
What differs:

- The path is the same family but not the same string.
- The persisted-query ID syntax is the same family (`<numeric>`)
  but the actual IDs differ and are undocumented.
- The response envelope differs: Google returns `[["wrb.fr",
  "<rpc>", "<payload>", ...]]` (positional). Meta returns
  `{"errors": [{"message": "..."}], "extensions": {"is_final":
  true}}` (GraphQL-style error envelope on failure; success
  envelope is undocumented because we never got a successful
  response).

The COMMON primitive is: `POST form-encoded body with a
persisted/opaque operation identifier`. The DIFFERENT primitive
is: how to discover the operation identifier (Google: pinned in
adapter code; Meta: unknown).

**Correction**: do not classify as a single capability. Use two
distinct entries:

- `POST form-encoded RPC envelope` — Google only (1 source, LIVE_FIXTURE = 0, CODE_ONLY via legacy adapter)
- `Persisted/opaque operation identifier discovery` — Google
  has stale hardcoded `r06xKb`; Meta has unknown doc_id; both
  need a primitive, but it is **not the same primitive** unless
  proven.

### 7.3 Capability evidence counts without live fixture

**Original claim**: "page_number: 5 sources. bootstrap: 3 sources."

**Reality**: Apple has LIVE_FIXTURE evidence (real `search.json`
captured). The legacy JobResearCHEF adapters (Workday, Oracle,
Radancy, SuccessFactors) are HISTORIC_LEGACY_FIXTURE evidence
(real saved fixtures in `tests/fixtures/` + test that consumed
them). These are TWO DIFFERENT evidence classes — both real,
but produced by different codebases.

The corrected evidence count policy is in section 4 of
`SOURCE_SPEC_GAP_ANALYSIS.md`.

---

## 8. Integrity statement (post-correction)

- 0 files in `JobResearCHEF/` modified
- 0 files in `runtime/` that are frozen (`spec_executor.py`,
  `source_spec.schema.json`, `job.schema.json`,
  `sources/mercedes.json`, `sources/nvidia.json`) modified
- 0 live HTTP requests issued
- 0 browser calls
- 121 PASS tests still green (42 frozen + 24 batch1 + 29 batch2
  revised + 26 batch3)


## 6. Migration plan

See companion file: `MIGRATION_PLAN.md`.
