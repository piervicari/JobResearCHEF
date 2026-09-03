# V2 implementation status

Updated: 2026-09-02

## Implemented in this iteration

### Network safety / canary

- `prepare-canary-db`: online integrity-checked disposable DB copy.
- `scan-canary --dry-run`: exact portal/host/URL preview with zero network requests and no operator-contact prerequisite.
- `scan-canary`: 1–3 explicit portals, sequential, concurrency 1, one-page cap, max 3 requests per portal, zero retries, 10s pause, automatic block-signal stop.
- Canary DB cannot be the configured production DB.
- `data/canary/*` runtime artifacts are gitignored.

### V2 discovery persistence

- `scan-discover`: no deterministic semantic filtering.
- Every discovered source job is persisted before AI processing.
- New/changed jobs become `PENDING_AI`.
- Existing lifecycle `first_seen_at`, `last_seen_at`, missing-successful-scan closure logic and observations are reused.
- Company raw text and resolved/group display label are kept separately.

### Payload / identity

- Application-owned `job-observation-v1` payload includes company, title, city/location, complete description, URLs, source/ATS/requisition IDs, job types, posted date and adapter.
- Native provider JSON is retained for audit but excluded from the canonical content hash.
- Same native source/ATS ID with conflicting title/location/apply URL is not silently merged.
- Source-ID collisions get a deterministic variant storage identity while preserving the native ID.

### Legacy offline preparation

- `prepare-v2-source-jobs` converts current legacy SourceJob rows without any career-site or LLM requests. The distributed V7 baseline DB is already converted.
- It backfills employer identity from the portal registry where possible.
- Shared portals use transparent group labels rather than pretending an exact child cluster is known.
- Existing payloads are converted to the V2 canonical envelope locally.

### JobAnalyzer framework

- `JobAiAnalysis` versioned table.
- `analyze-pending --dry-run` previews jobs/request count plus `missing_company` with zero LLM calls. Live analysis fails closed before any API call if selected jobs still lack company identity.
- `analyze-pending` uses explicit task-difficulty routes with Google primary models, same-model transient retry where configured, schema micro-repair, and OpenRouter/MiniMax cross-provider fallback; structured JSON remains strict.
- Model is deliberately not hardcoded.
- Failed LLM batches remain local `PENDING_AI`; no career-site rescan is required.
- Analysis is bound to model + prompt + schema + input payload hash.

## Validation performed here

- 26/26 targeted payload/dedup/lifecycle/JobAnalyzer/router tests passed in the sandbox (using a minimal local `selectolax` stub only because the package is unavailable here).
- 88 Python source/test files compile without syntax errors.
- The packaged 5,789-row project DB was converted offline to V2 payload/company identity; a second dry-run is idempotent (0 further payload/company changes).
- Canary dry-run verified portal IDs 69/514/217 map to KPMG/PayPal/Mercedes-Benz with zero network access.
- Full historic pytest suite was not rerun in this sandbox because `selectolax` is absent and package installation has no network access. Existing project virtualenv is macOS/ARM and cannot be executed here.

## Still P0

1. Run the five-employer end-to-end pilot (`scripts/run_p0_pilot.sh`) from the user network.
2. Inspect cyber yield, parser coverage, LLM failures and any `NEEDS_MORE_DETAIL` rows from the generated report.
3. Improve detail-page retrieval only where the pilot proves descriptions are insufficient.
4. If the pilot is clean, expand incrementally through the curated 200-employer core rather than generic company waves.
5. Keep the new `AI Cyber V2` dashboard view as the product path; legacy CanonicalJob views remain historical compatibility only.

The five-job AI micro-canary is accepted as sufficient P0 evidence. Gemini 3.6 Flash classified 1 cyber and 4 non-cyber jobs correctly enough to proceed; model-vs-model benchmarking is not a blocker. The raw report is stored at `docs/reports/ai_micro_canary_20260902-134348.log`.

## Explicitly not yet done

- no full/core live scan; only low-impact canaries completed;
- live LLM micro-canary completed; no broad AI run yet;
- no Telegram;
- no scheduler;
- no AI/SWE domain expansion;
- no broad new company wave.


### 2026-09-02 LLM canary follow-up

The first five-job live batch completed through Gemini 3.6 Flash after Gemini 3.7 Flash returned 503 and a same-model retry timed out. V10 added immediate live routing progress, bounded per-target timeouts, and disabled same-model retry on the MEDIUM job-analysis route. V11 additionally enforces free-only routing: paid OpenRouter fallbacks are rejected and MiniMax-M3:free is the cross-provider fallback. Decisions: `0020-live-llm-progress-bounded-timeouts-and-medium-fast-fallback.md` and `0021-free-only-llm-routing.md`.

### V14 P0 product-path additions

- Stable `~/.config/research-agent/.env` secrets loading + one-time `bootstrap-secrets` migration.
- Harmless project-local `.env` distributed with no credentials.
- `prepare-pilot-db`: clean disposable DB that preserves company/portal registry but removes legacy job/run state.
- `scan-pilot`: <=5 explicit/default low-criticality portals, sequential, <=3 requests/portal, one page, <=10 jobs, zero retry, immediate block-signal stop, PENDING_AI persistence.
- `scripts/run_p0_pilot.sh`: one-command network + AI end-to-end test with a shareable log file.
- Dashboard `AI Cyber V2` tab reading SourceJob + latest JobAiAnalysis directly; all cyber seniorities retained.
- `show-ai-results --status CYBER` for local product-view inspection.

## 2026-09-02 P0 end-to-end pilot result

The first five-employer P0 pilot completed successfully end-to-end. Evidence is stored in `docs/reports/p0_end_to_end_pilot_20260902-140011.log`.

- 5 portals scanned with 8 total HTTP requests.
- 8/8 requests returned HTTP 200; 0 retries; 0 access-control signals.
- 36 SourceJob rows persisted.
- 36/36 analyzed across four LLM batches.
- One Gemini 3.6 HTTP 503 fell through to MiniMax M3 :free, which succeeded; no batch was lost.
- 4 CYBER, 24 NON_CYBER, 8 NEEDS_MORE_DETAIL.

The pilot therefore validates the V2 separation of network acquisition, durable local queueing and LLM processing. It also found the next P0 bottleneck: generic/detail data quality.

### Implemented immediately after pilot

- Added selective `enrich-details` path for CYBER/NEEDS_MORE_DETAIL jobs whose descriptions are too short. Initial implementation is same-host, robots-aware, sequential, no-retry and bounded.
- Added explicit `detail_*` SourceJob provenance fields rather than pretending listing metadata and fetched detail data are the same observation.
- AI analysis input hashing now uses the effective enriched input so changed detail can be re-analyzed without uniqueness collisions.
- Latest result views return one current JobAiAnalysis per SourceJob while retaining historical analyses.
- Generic HTML navigation exclusions now reject `Find Jobs` / `Find a job` / `Job openings` pseudo-vacancies.
- Corrected Trellix from generic branded homepage to its official Workday `EnterpriseCareers` route via audited registry Run 27.
- Added `docs/CODEX_HANDOVER_CURRENT.md` as the cumulative current-state handover.

### Immediate validation command

Run `./scripts/run_p0_detail_followup.sh` from the next baseline. It reuses the most recent sibling pilot DB, performs a five-job detail-enrichment canary, re-analyzes only changed rows and writes one report under `output/test_runs/`.

## V18 follow-up hardening (2026-09-02)

- embedded Cloudflare Turnstile widgets no longer cause false page-level `AccessChallengeError` by themselves;
- substantive descriptions are contractually forced to a binary CYBER/NON_CYBER semantic decision;
- selective detail enrichment defaults to at most 2 detail pages per host per run;
- first selective-detail pilot evidence preserved in `docs/reports/p0_detail_followup_20260902-153411.log`.


### V20 free-provider routing hardening (2026-09-02)

- MiniMax M3 `:free` is primary for active semantic routes.
- One same-target retry is allowed only with explicit OpenRouter `Retry-After` (bounded 90s).
- MiniMax M2.7 `:free` is a second free fallback; Gemini 3.6 Flash is final cross-provider fallback.
- `analyze-pending` now returns non-zero when any selected batch fails, while preserving failed rows as `PENDING_AI`.

## 2026-09-02 — P0 technical validation complete; first core expansion prepared

The AI-resume run validated MiniMax Retry-After retry, JSON micro-repair, enriched-input persistence and zero-loss PENDING_AI recovery. P0 is no longer blocked on provider mechanics. V21 adds targeted cleanup for fully-described stale NEEDS_MORE_DETAIL rows and `scripts/run_p0_core_expansion.sh` for the first bounded 10-employer core expansion. See decisions 0040–0041 and `docs/CODEX_HANDOVER_CURRENT.md`.

## V22 operator workflow stabilization (2026-09-02)

- Runtime SQLite state moved to `~/.local/share/research-agent/research_agent.db` by default; seeded once from the newest prior pilot DB and migrated additively.
- `scripts/ensure_dashboard.sh` starts Streamlit only when it is not already healthy on the correct managed runtime DB.
- `scripts/run_core_trial.sh` is now the preferred one-command operator path for the first controlled core expansion.
- Dashboard shows the active DB URL and has a manual refresh control.
- This removes repeated cross-ZIP database copying from the normal workflow while preserving historical bootstrap/recovery helpers.

## V23 — Stripe ATS correction + large-catalog semantic triage (2026-09-02)

The first 10-employer core run proved network stability but exposed discovery gaps on custom career portals. Stripe is the first corrected employer in the one-by-one verification loop.

Implemented:

- Stripe cluster `CG-2FCB5A43A4` corrected through the audited registry-change path from `stripe.com/careers/search` to operational Greenhouse board token `stripe`, while retaining Stripe careers as the canonical landing page.
- New synchronized master: `data/company_universe/master_company_universe_v1_12_stripe_greenhouse.csv`.
- One-shot Greenhouse/Ashby catalogs can retain up to `bulk_catalog_max_jobs_per_portal` records without weakening HTTP request/page budgets.
- New high-recall `triage-pending` semantic stage, default 100 jobs/request, MiniMax M3 :free first. Clearly non-cyber jobs are removed from the rich-analysis queue; possible/ambiguous cyber jobs remain `PENDING_AI`.
- Triage and rich analysis can be portal-scoped via repeated `--portal-id` flags.
- `show-portal-jobs` provides an employer/portal-local inventory for external ground-truth comparison.
- `scripts/run_stripe_greenhouse_probe.sh` is the next operator command and produces a single shareable report.

Validation in this build: 19/19 targeted JobAnalyzer/router/triage/Greenhouse tests pass in the sandbox; Python compile and shell syntax checks pass. The full ATS suite still cannot collect here because `selectolax` is not installed in the sandbox, but the user's `uv sync --dev` installs it on macOS.


## V24 — Google Careers structured source + semantic precision hardening (2026-09-02)

- Narrowed CYBER semantics in both LLM stages: financial fraud/AML/KYC/KYB/financial crime, credit risk, generic enterprise/operational risk and generic legal/regulatory compliance are excluded unless the actual core work is information/cyber security. No deterministic keyword exclusion is used. Prompt versions: `cyber-triage-v2`, `cyber-job-v4`.
- Added shared form-encoded POST support to `HttpFetcher`.
- Added `GoogleCareersAdapter` for the verified Google Careers platform signature, using the anonymous frontend `batchexecute` search RPC (`r06xKb`) rather than generic HTML. Search records carry descriptions/responsibilities/qualifications and stable job IDs.
- Added strict schema handling and tests for Google positional records, pagination completeness and platform-based registry selection.
- Added `scripts/run_google_careers_probe.sh`: persistent DB + managed dashboard + zero-network adapter preflight + sequential full catalog scan + 100-job triage + candidate-only full analysis + one shareable log.
- Google-only scan envelope: concurrency 1, min interval 1.25s, max 200 pages / 220 requests, structured record cap 5,000. Global scanner defaults are unchanged.
- Validation in build sandbox: compile succeeds and 23 targeted tests pass. Full dependency/test sync was blocked by a sandbox download timeout for `greenlet`, so this is not a full-suite certification.

Next gate: run `./scripts/run_google_careers_probe.sh`, upload the log, then compare its Google CYBER inventory against current web-visible Google security vacancies before PASS/FIX and before moving to Microsoft.
