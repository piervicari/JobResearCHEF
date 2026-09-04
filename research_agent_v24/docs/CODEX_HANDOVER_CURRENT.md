# CODEX HANDOVER — RESEARCH AGENT PIER — CURRENT STATE

**Updated:** 2026-09-02 — V24 prepared after Stripe PASS; Google structured-RPC probe is next  
**Read this file first.** Then read `docs/ROADMAP_V2.md` and only the ADRs in `docs/decisions/` needed for rationale.

## 1. Product objective

Build a local-first research agent that monitors a manually curated set of important employers through their **official career sites / ATS sources**, retains **all cybersecurity jobs regardless of seniority**, and uses an LLM rather than deterministic keyword logic to interpret job semantics. The resulting private dataset is used both for finding current early-career opportunities and for reverse-engineering skills across the full career ladder.

Current domain: **cybersecurity only**. AI and SWE are future domain labels; overlap support is desired later.

Automated LinkedIn scraping is out of scope. Existing manual LinkedIn CSV import may remain.

## 2. Non-negotiable design decisions

1. **Target employers are human curated.** No automatic company ranking decides membership. Current pilot core = 200 employers; membership and scan cadence are separate concepts.
2. **Store every discovered source job durably before semantic decisions.** `SourceJob` is the discovery queue.
3. **No deterministic cyber/seniority/geography gate in V2.** Code owns HTTP, parsing, normalization, identity, dedup, persistence and lifecycle. LLM owns semantic job interpretation.
4. **All cybersecurity seniorities are retained.** Senior/staff/principal/manager jobs are valuable for skill reverse-engineering.
5. **Raw source evidence and AI interpretation are separate/versioned.** Never overwrite historical AI evidence as if it were source truth.
6. **Prefer duplicate over lost vacancy.** Job identity is location-aware and source-ID conflicts are preserved as variants.
7. **Official sources first.** Structured ATS/API adapters are preferred; generic HTML is fallback.
8. **Network behavior is conservative.** No rotating proxies, fingerprint spoofing, CAPTCHA bypass or generic browser automation.
9. **LLM routing is free-only.** Full analysis: MiniMax M3 `:free` -> MiniMax M2.7 `:free` -> Gemini 3.6 Flash. Triage: MiniMax M3 `:free` -> MiniMax M2.7 `:free` -> Gemini 3.5 Flash-Lite. MiniMax M3 may retry once only when an upstream `Retry-After` is supplied.
10. **Runtime state is persistent across code versions.** DB: `~/.local/share/research-agent/research_agent.db`; secrets: `~/.config/research-agent/.env`. Project-local `.env` is only a bootstrap fallback and secrets must never be logged.

## 3. Current V2 architecture

```text
curated employer registry
        ↓
official ATS / career-site scanner
        ↓
SourceJob (durable discovery, PENDING_AI)
        ↓
JobAnalyzer batch route
        ↓
CYBER | NON_CYBER | NEEDS_MORE_DETAIL
        ↓
if CYBER/NEEDS_MORE_DETAIL and description is weak:
selective same-host detail enrichment
        ↓
PENDING_AI again when detail changes
        ↓
AI re-analysis
        ↓
AI Cyber V2 dashboard / local queries
```

Legacy `scan-official` and `VacancyFilter` code remain for historical compatibility. **Do not use them as the V2 product path.**

## 4. Current data model essentials

### SourceJob
Stores discovery/source identity and lifecycle. Important fields include:

- source/native/ATS/requisition IDs;
- source/apply/canonical apply URL;
- raw title/company/location/country/city/employment/workplace/description;
- resolved company/cluster identity;
- first_seen_at / last_seen_at / is_active / missing_successful_scans / closed_at;
- payload_sha256 + raw_payload_json;
- ai_status / ai_attempts / ai error timestamps;
- **new detail enrichment fields:** detail_title/location/country/city/employment/workplace/description/url/payload hash/fetched_at.

Listing/raw observation remains distinguishable from second-stage detail data.

### JobAiAnalysis
Versioned structured semantic analysis. AI input hash is now computed from the **effective input** (detail fields preferred over listing fields), not merely the listing observation hash. This allows legitimate re-analysis after detail enrichment using the same model/prompt/schema.

### JobObservation
Immutable scan observation. Existing payload-change optimization is retained so unchanged descriptions are not duplicated every scan.

## 5. JobAnalyzer contract

Current output:

- is_cybersecurity
- needs_more_detail
- role_family
- specializations
- seniority
- years_experience_min/max
- skills_required/preferred
- degree_requirement
- certifications
- short_reason

Rules: all seniorities valid; null > guessing; exact batch job IDs required; schema validated locally.

## 6. Current LLM routing

Normal `job_analysis`:

1. `openrouter/minimax/minimax-m3:free` thinking=medium, timeout 300s; one same-target retry **only** when upstream supplies explicit `Retry-After`, bounded to 90s.
2. `openrouter/minimax/minimax-m2.7:free` thinking=medium, timeout 300s, no retry.
3. `google/gemini-3.6-flash` thinking=high, timeout 300s, no retry.

OpenRouter free-only guard rejects non-`:free` targets. Live progress/Retry-After waits are printed and persisted in test reports. JSON/schema micro-repair is separate and currently uses Gemini 3.5 Flash-Lite when needed. Gemini 3.7 remains temporarily disabled from active routes.

## 7. Empirical validation completed

### Network canaries
KPMG / PayPal / Mercedes: five total 2xx requests, zero retries/403/429/challenges. Mercedes proved access health != extraction health.

### Five-job AI micro-canary
Gemini 3.6 classified a mixed Apiiro batch coherently: one cyber security/AI role and four non-cyber roles. Accepted; no model-vs-model benchmark blocker.

### P0 end-to-end pilot — 2026-09-02
Evidence: `docs/reports/p0_end_to_end_pilot_20260902-140011.log`.

- cohort: Detectify, Trellix, Horizon3.ai, Safe Security, Wazuh;
- network: 8 requests, all HTTP 200, 0 retries/block signals;
- persistence: 36 new SourceJob rows;
- AI: 4 batches, 36/36 analyzed;
- routing: 3 Gemini batches successful; one Gemini 503 fell through to MiniMax which succeeded in ~10s;
- output: 4 CYBER, 24 NON_CYBER, 8 NEEDS_MORE_DETAIL.

**Pilot conclusion:** architecture works; broad scale-out is gated by source/detail quality, not by LLM routing or network access.

## 8. Issues discovered by P0 pilot

### A. Generic HTML often has title/URL only
Detectify and Wazuh produced rows with zero description. Two obvious CYBER roles were classified from title alone, leaving skills/experience empty. This is unacceptable for the skill-mining objective.

**Implemented baseline:** `enrich-details` selects CYBER first, then NEEDS_MORE_DETAIL, only when description is short. Initial implementation is same-host and robots-aware, bounded/sequential/zero-retry, and stores second-stage detail provenance separately. Changed detail requeues the job as PENDING_AI.

### B. Trellix false job `Find Jobs`
The generic adapter treated a navigation link as a vacancy.

**Fixes:**
- generic navigation exclusion expanded (`Find Jobs`, `Find a job`, `Job openings`);
- Trellix registry corrected from branded homepage to official `EnterpriseCareers` Workday endpoint via audited Run 27;
- synchronized master: `master_company_universe_v1_11_registry_corrections_run27.csv`.

### C. Re-analysis views can duplicate historical AI records
Detail enrichment intentionally creates new AI analyses.

**Fix:** operational `show-ai-results` selects only the latest JobAiAnalysis per SourceJob. Historical analyses remain in DB.

## 9. Network safety policy for detail enrichment

Do not prefetch every job description.

- first-pass listing scan is cheap;
- first-pass AI chooses relevance/ambiguity;
- enrich only CYBER or NEEDS_MORE_DETAIL jobs with insufficient descriptions;
- CYBER is prioritized because skill extraction requires evidence even if title classification is obvious;
- same-host only in initial generic implementation;
- robots-aware;
- concurrency 1;
- no retries;
- small explicit limit (default 5 in the follow-up pilot);
- 10s spacing.

## 10. Exact next validation task — V24

Stripe is technically validated and no longer the next probe. The next Tier-S employer is **Google**.

Before the Google probe, V24 narrows the semantic CYBER boundary in both triage and full analysis: payment/merchant fraud operations, AML/KYC/KYB/financial crime, credit risk, generic enterprise/operational risk and generic regulatory/legal compliance are NON_CYBER unless the actual work is information/cyber security. This is implemented in the LLM contract, not deterministic regex. Prompt versions are `cyber-triage-v2` and `cyber-job-v4` (decision 0048).

Google Careers is not scanned through generic HTML. Current research found the anonymous structured BOQ `batchexecute` RPC used by the careers frontend. V24 adds `GoogleCareersAdapter`, selected from the verified Google Careers host/path + `Custom Google Careers` platform signature rather than from company identity. Search RPC `r06xKb` exposes source IDs, title, apply URL, locations, description/responsibilities/qualifications and timestamps, so the initial catalog does not perform one detail request per job (decision 0049).

Because Google fixes search pages at 20 jobs, a full catalog around 3.5k jobs requires roughly 175 POSTs. Do not raise global scanner limits. The Google probe alone uses sequential concurrency=1, 1.25s minimum pacing, max 200 pages / 220 requests and a 5,000-record cap; incomplete scans remain explicitly incomplete and cannot advance closure lifecycle (decision 0050).

Run exactly:

```bash
./scripts/run_google_careers_probe.sh
```

The script:

1. syncs dependencies and bootstraps persistent secrets/runtime DB;
2. ensures the managed Streamlit dashboard without spawning duplicates;
3. resolves Google/Alphabet cluster `CG-C65DC3B9A9` to its active portal;
4. performs a zero-network adapter-selection preflight;
5. scans the complete structured Google Careers catalog under the probe-scoped budget;
6. prints catalog/description/dedup statistics;
7. triages all pending Google jobs in batches of 100;
8. full-analyzes only candidates in batches of 10;
9. prints final CYBER jobs and writes `output/test_runs/google_careers_probe_*.log`.

After the operator uploads that log, independently verify current Google security vacancies on the web and compare catalog coverage, missed jobs, false positives and duplicates before declaring Google PASS/FIX. **Do not move to another Tier-S employer before that comparison.**

## 11. P0 after the detail follow-up

If selective enrichment produces full descriptions/skills without access-control signals:

1. implement/verify detail extraction for the most common structured adapters that do not include descriptions in listing responses (Workday is first priority; SuccessFactors/SmartRecruiters/Radancy/Avature follow based on actual core coverage);
2. expand scanning **incrementally** across the curated 200-employer core, not the generic 11,798-cluster universe;
3. collect coverage/yield metrics;
4. keep Telegram/scheduling deferred until manual scanning is demonstrably useful.

## 12. Files Codex should read

1. `docs/CODEX_HANDOVER_CURRENT.md` — this file.
2. `docs/ROADMAP_V2.md` — current product roadmap.
3. `docs/V2_IMPLEMENTATION_STATUS.md` — implementation status.
4. `docs/decisions/README.md` — ADR index.
5. decisions 0011, 0012, 0014, 0016, 0021, 0023, 0027–0030.
6. `docs/reports/p0_end_to_end_pilot_20260902-140011.log` — empirical evidence.

Do not infer current intent from the old root `CODEX_HANDOVER_RESEARCH_AGENT_PIER.md`; it describes the pre-V2 deterministic milestone and is historical context only.

## 13. Operational portability fix after first detail-follow-up attempt

The first `run_p0_detail_followup.sh` attempt stopped before any network or LLM request because `scripts/bootstrap_latest_pilot_db.sh` used a bare `python` executable and macOS did not expose `python` on PATH.

**Fix in V16:** embedded Python in that operational script now runs via `uv run python`. A shell-script audit found no other bare Python dependency requiring correction (`final_audit.sh` already uses `uv run python`). See decision 0032.

The intended next task is unchanged: rerun `./scripts/run_p0_detail_followup.sh` and review the generated `p0_detail_followup_*.log` before expanding employer coverage.

## Update — 2026-09-02: imported pilot DB schema migration

The first V16 detail-follow-up run imported the prior P0 pilot DB successfully but stopped before network/LLM work because the older SQLite schema did not contain the newly introduced `source_jobs.detail_*` columns. Decision 0033 fixes this by running the existing additive `create_schema`/`init-db` migration automatically immediately after a prior pilot DB is copied. Do **not** recreate/rescan the P0 pilot to solve this; preserve the existing 36 jobs and analyses and migrate the DB offline.

## Update — 2026-09-02: first selective-detail follow-up completed

Evidence: `docs/reports/p0_detail_followup_20260902-153411.log`.

Observed results:

- imported/migrated previous pilot DB successfully;
- five detail candidates selected;
- Detectify: 3/3 detail pages parsed successfully via JSON-LD, yielding 4.5k–5.8k character descriptions and Stockholm location;
- Wazuh: HTTP 200 detail page was falsely treated as an access challenge because the page embeds Cloudflare Turnstile around its application form; subsequent Wazuh candidate was skipped by the host circuit;
- re-analysis used Gemini 3.6 first, timed out at 300s, then MiniMax M3 `:free` succeeded in ~4.4s;
- Detectify Cyber Security Solutions Engineer became a rich CYBER record with skills, experience and specializations;
- two fully-described Detectify engineering roles remained `NEEDS_MORE_DETAIL` even though the model reason itself described them as primarily non-cyber. This is an AI-contract inconsistency, not missing source data.

Important correction: the Wazuh URL `/job/senior-software-engineer-cti/` is not evidence of a wrong title/URL pairing; Wazuh currently serves the `Threat Intelligence analyst` posting at that legacy slug. Do not "fix" the generic anchor association based on slug/title mismatch alone.

V18 decisions/fixes:

1. **0034:** `cf-turnstile` alone is no longer a hard access-challenge marker; strong challenge/interstitial signals remain blocking.
2. **0035:** substantive descriptions (>=1,000 chars for current P0 guardrail) cannot remain `NEEDS_MORE_DETAIL`; the semantic model must classify CYBER or NON_CYBER. Local validation routes contradictory output through repair/fallback instead of persisting it.
3. **0036:** detail enrichment defaults to at most two detail pages per host per run, retaining the conservative canary posture.

### Exact next task after V18

Run `./scripts/run_p0_detail_followup.sh` again. The bootstrap must reuse the **latest** sibling pilot DB containing the successful Detectify enrichment, so Detectify should not be fetched again. The next dry run should primarily select at most two Wazuh detail pages because of the new per-host cap. Review the resulting log before expanding employer coverage.

If Wazuh details are successfully parsed and the re-analysis produces binary CYBER/NON_CYBER decisions for substantive descriptions, consider P0 detail-enrichment behavior validated enough to start an incremental core-employer cohort expansion.


## Update — 2026-09-02: Wazuh detail fetch succeeded; AI persistence hash bug fixed

Evidence: `docs/reports/p0_detail_followup_20260902-155606.log`.

Observed results:

- Wazuh Turnstile false-positive fix worked: two targeted detail pages returned HTTP 200 and were parsed successfully;
- Threat Intelligence analyst: ~3,969 chars, Remote; Business Development Account Manager: ~3,200 chars, Remote;
- detail network work completed successfully with 3 requests total (robots + two details), zero retries/failures;
- Gemini 3.6 timed out after 300s, MiniMax M3 `:free` returned a valid result in ~7s;
- persistence then failed on `uq_job_ai_analysis_input_version`.

Root cause: `_analysis_input()` computed the correct effective enriched-input hash, but `analyze_pending_jobs()` stored the old `SourceJob.payload_sha256`. This made a genuinely new enriched analysis look identical to the old listing-only analysis.

V19 / decision 0037 fixes this by persisting `AnalysisInput.payload_sha256`, making exact same-version writes idempotent, and bumping the semantic prompt contract to `cyber-job-v3`.

### Exact next task after V19

Do **not** run another detail-follow-up first. The latest sibling pilot DB already contains the successful Wazuh detail fetches and marks those jobs `PENDING_AI`. Run `./scripts/run_p0_ai_resume.sh`. It imports the latest pilot DB and performs zero career-site requests; it only resumes AI processing and writes a `p0_ai_resume_*.log`. Review that log before fetching further Wazuh details or expanding employer coverage.


## Update — 2026-09-02: AI resume exposed free-provider availability gap

Evidence: `docs/reports/p0_ai_resume_20260902-161701.log`.

Observed results:

- no career-site requests occurred; the two enriched Wazuh jobs remained safely `PENDING_AI`;
- Gemini 3.6 Flash spent ~206 seconds before returning HTTP 503 high-demand;
- MiniMax M3 `:free` then returned HTTP 429 from an upstream shared pool, with an explicit `Retry-After: 60`;
- all routes failed, so zero analyses were persisted and the two jobs remained pending;
- the old CLI nevertheless returned process exit 0, making the wrapper report `ai_exit_code: 0`.

V20 decisions/fixes:

1. **0038:** active semantic routes become MiniMax M3 `:free` -> MiniMax M2.7 `:free` -> Gemini 3.6 Flash. M3 may retry exactly once only when OpenRouter supplies `Retry-After`, bounded to 90 seconds.
2. **0039:** any AI batch failure makes `analyze-pending` return non-zero (code 2) after printing metrics/telemetry; failed jobs remain `PENDING_AI`.
3. Free-only enforcement remains mandatory; no paid model is introduced.

### Exact next task after V20

Run `./scripts/run_p0_ai_resume.sh`. It must import the latest pilot DB and perform **zero career-site requests**. Expected pending set remains Wazuh job IDs 27 and 36 unless a later sibling DB has already resolved them. Review the generated `p0_ai_resume_*.log`.

If the two enriched jobs are classified successfully and persistence is clean, stop micro-testing provider mechanics and proceed to the first incremental core-employer expansion cohort.


## Update — 2026-09-02: P0 AI resume succeeded; transition to core expansion

Evidence: `docs/reports/p0_ai_resume_20260902-164636.log`.

Observed results:

- zero career-site requests; enriched Wazuh rows were reused from the local pilot DB;
- MiniMax M3 first attempt returned upstream-shared-pool 429 with `Retry-After: 60`; router waited exactly 60s and retried once;
- second MiniMax M3 attempt returned HTTP 200; JSON micro-repair via Gemini 3.5 Flash-Lite succeeded;
- Business Development Account Manager became NON_CYBER; Threat Intelligence analyst became a rich CYBER record;
- `still_pending_jobs=0`, `api_failures=0`, persistence clean.

This validates the P0 provider retry/fallback/repair/persistence mechanics sufficiently to stop provider micro-tests.

Two Detectify rows remain `NEEDS_MORE_DETAIL` despite substantive descriptions because their persisted analyses predate the cyber-job-v3 binary-decision contract. Decision 0040 adds a narrow offline semantic cleanup: requeue only substantive `NEEDS_MORE_DETAIL` rows instead of replaying every historical prompt version.

### Historical next task after V21 (completed)

At V21 the next command was `./scripts/run_p0_core_expansion.sh`. It:

1. imports/migrates the latest pilot DB;
2. previews and requeues only contract-inconsistent fully-described `NEEDS_MORE_DETAIL` rows;
3. scans the 10-employer core expansion cohort in two five-portal groups using the existing low-impact safety envelope;
4. analyzes the resulting pending queue in batches of 10;
5. prints full CYBER and remaining NEEDS_MORE_DETAIL results;
6. writes `output/test_runs/p0_core_expansion_*.log`.

Do not return to isolated provider/detail micro-tests unless this larger cohort exposes a new concrete failure.

## Update — 2026-09-02: persistent runtime state + dashboard supervisor (V22)

Decisions 0042–0043 remove version-folder DB copying from the normal operator path. Mutable runtime state now defaults to `~/.local/share/research-agent/research_agent.db`; the first V22 run seeds it once from the newest prior pilot DB and runs additive schema migration. Subsequent code ZIPs should reuse this DB rather than copying state forward again.

The existing Streamlit dashboard is now part of the normal P0 operator path. `scripts/ensure_dashboard.sh` checks `http://127.0.0.1:8501/_stcore/health`, starts Streamlit only when necessary, and always binds managed instances to the persistent runtime DB. `scripts/run_core_trial.sh` is the preferred one-command entry point: dependency sync (including the dashboard extra) -> secrets -> persistent DB -> dashboard -> first 10-employer core expansion. It does not relaunch a healthy managed dashboard already using the correct DB.

### Current project path

- **P0 technical mechanics:** validated (scanner -> SourceJob -> LLM routing/retry -> detail enrichment -> persistence -> AI-first dashboard).
- **Current step:** employer-by-employer Tier-S portal validation; Stripe discovery passed, Google is the active V24 target.
- **Next P0 work:** run the Google probe, independently compare against current web-visible Google security vacancies, mark PASS/FIX, then proceed to Microsoft. Resolve adapter/backend gaps one employer at a time rather than another broad custom-portal batch.
- **P1:** real-job golden set, precision/recall and lifecycle/dedup reliability gates.
- **P2:** internship/program historical intelligence.
- **P3:** scheduler/Telegram and later AI/SWE domain expansion.

Do not reintroduce version-folder DB copying as the default unless persistent runtime state proves unsafe.

## Update — 2026-09-02: first 10-employer core expansion exposed portal-resolution bottleneck

Evidence: `docs/reports/p0_core_expansion_20260902-172532.log`.

Observed results:

- network posture remained healthy: all core-trial career requests returned HTTP 200; no 403/429/challenge/retry events;
- Workday adapters (Proofpoint, Airbus) produced real structured jobs;
- Snyk, Arctic Wolf, Abnormal Security, Claroty, Stripe and Datadog returned `EMPTY_INCOMPLETE` through generic HTML — this is a discovery/adapter gap, NOT evidence of zero vacancies;
- Visa/GitLab generic HTML produced navigation/CTA false jobs;
- MiniMax M3 completed all three full-analysis batches successfully with no fallback;
- the architectural bottleneck has shifted from LLM plumbing to corporate-careers -> ATS/backend resolution.

### V23 Stripe correction and call-count optimization

Stripe is the first one-employer resolution pass:

1. Stripe careers remains the canonical employer-facing page.
2. Operational source is corrected through the Registry Change mechanism to Greenhouse board token `stripe` (decision 0044).
3. Greenhouse/Ashby one-shot structured catalogs no longer inherit the 10-record HTML pilot cap; request/page budgets remain conservative (0045).
4. Large catalogs enter a high-recall MiniMax-first semantic triage at 100 jobs/request before rich 10-job full analysis (0046). No deterministic semantic filter is reintroduced.
5. `triage-pending` and `analyze-pending` accept portal filters so a company probe cannot consume unrelated pending queues.
6. `scripts/run_stripe_greenhouse_probe.sh` was the V23 operator task and has completed successfully: 1 Greenhouse request -> 592 jobs with 592 descriptions; 6 triage calls -> 78 candidates; 8 full-analysis calls -> 26 CYBER before the V24 semantic-boundary correction.
7. After Stripe passes, proceed employer-by-employer. The user supplies each probe log; independently verify current official web vacancies against scanner output before marking the portal covered (0047).

### Historical V23 command (completed)

`./scripts/run_stripe_greenhouse_probe.sh`

Do not run another broad 10-employer expansion until the one-by-one portal verification loop has established whether each custom portal needs ATS resolution, an adapter, or only a generic-parser correction.


## Update — 2026-09-02: V24 Google structured-source probe prepared

Stripe V23 established the employer-by-employer validation loop and passed discovery: one Greenhouse request returned 592/592 described vacancies. Its main remaining defect was semantic precision: financial-fraud/AML/generic-risk roles were leaking into CYBER. V24 fixes that boundary through the versioned LLM contract (`cyber-triage-v2`, `cyber-job-v4`), preserving high-recall ambiguity handling and avoiding keyword exclusions. See decision 0048.

Google is now the next Tier-S target. Current Google Careers research found a public anonymous frontend RPC rather than a documented external ATS API. V24 adds a strict positional `GoogleCareersAdapter` around the observed `batchexecute` search RPC `r06xKb`; adapter selection is based on the careers platform signature, not a Google company special-case. Search records already carry descriptive fields, so there is no bulk detail-page fan-out. See decision 0049.

Google's 20-record pagination makes its full catalog materially more request-heavy than Stripe. V24 therefore leaves global scanner budgets untouched and scopes the larger 200-page/220-request envelope to `scripts/run_google_careers_probe.sh`, sequential and paced. See decision 0050.

Local validation for this change: Python compile succeeded and 23 targeted tests covering Google parsing/pagination/platform selection, form-encoded HTTP POST support, and the narrowed triage/full-analysis contracts passed. A full dependency/test run was not completed in the build sandbox because `uv sync` timed out downloading `greenlet`; do not misreport this as a full-suite pass.

**Current operator action:** `./scripts/run_google_careers_probe.sh`, then upload the generated log for independent web ground-truth comparison.

## Update — 2026-09-03: V26-prep — conservative codebase cleanup + first end-to-end smoke

A conservative cleanup pass was performed in two phases.

### Phase 1 — Validation on the as-is codebase (no deletions)

- `uv run python -c "import research_agent; from research_agent.cli import app"` → `import_ok`.
- `uv run pytest -q` → **250 / 250 PASS** (test count before).
- `uv run ruff check src tests` → 89 pre-existing violations (E501 line length, I001 import sort, F401 unused imports, UP035 `Callable` from `typing`); all are non-blocking and unrelated to behaviour.
- `bash scripts/prepare_tier_s_operational_sources.sh` → V25.1 CORE_200 acceptance gate PASS; `tier_s_operational_sources_status: ok` (200 distinct CORE_200, 26 CORE_EXTENSION, 145 source-less HOLD, 62 READY_TO_PROBE).

### Phase 1.5 — Real smoke test (three employers, three ATS)

Run sequentially, never in parallel, against a snapshot of the persistent runtime DB at `/tmp/research_agent_smoke.db` (the persistent DB itself was not modified). Full log: `output/test_runs/product_smoke_20260903-151039.log`.

| Employer | ATS | Adapter | Portal ID | HTTP requests | HTTP status | Jobs discovered | New | Description coverage | `complete_snapshot` | Triage calls | Full-analysis calls | CYBER | NON_CYBER | NEEDS_MORE_DETAIL | PENDING/ERROR |
|---|---|---|---|---:|---:|---:|---:|---:|:-:|---:|---:|---:|---:|---:|---:|
| Stripe | Greenhouse | `greenhouse` | 535 | 1 | 200 | 601 | 35 | 614/614 | True | 3 (25 jobs) | 0 (triage marked all 25 as obvious_non_cyber on top of the existing CYBER records) | **26** | 588 | 0 | 0 |
| OpenAI | Ashby | `ashby` | 551 | 1 | 200 | 30 | 30 | 30/30 | False (bounded) | 3 (30 jobs) | 2 (7 candidates) | **5** | 25 | 0 | 0 |
| NVIDIA | Custom HTML (no Workday portal in DB) | `official_html` | 443 | 2 (robots + careers) | 200 | 0 | 0 | 0/0 | False (`no JSON-LD JobPosting or high-confidence job links found`) | 0 | 0 | 0 | 0 | 0 | 0 (EMPTY_INCOMPLETE) |
| Proofpoint (Workday reference) | Workday | `workday` | 265 | 9 (consecutive paging) | 200 | 146 | 136 | **0/146** | True | 3 (30 jobs) | 6 (30 candidates) | 1 | 25 | 30 | 90 |

`smoke_status: PASS`. Dashboard `queries.coverage_summary` and a direct SQL smoke against `SourceJob` / `JobAiAnalysis` confirm all four portals are readable without launching Streamlit.

### Notable smoke observations

- **NVIDIA has no Workday portal in the persistent DB.** Cluster `CG-05F5439F98` only maps to the custom HTML careers page; the custom HTML adapter is the expected path and yields `EMPTY_INCOMPLETE` (JS-rendered page, not in scope per ADR 0008). A bounded Proofpoint/Workday probe was added as the empirical Workday-adapter reference; the Workday adapter path is functional.
- **OpenAI Ashby response is 12.6 MB** (default `max_response_bytes=10MB` rejected it). The smoke test sets `RESEARCH_AGENT_SCANNER__MAX_RESPONSE_BYTES=20000000` to allow it. This is an envelope observation; no code change.
- **Workday listing responses do not include descriptions** (0/146). All 30 fully-analyzed rows hit `NEEDS_MORE_DETAIL`. This is the known detail-enrichment gap; the existing `enrich-details` path targets the same host for the candidates, with the per-host safety cap of decision 0036.
- **AI routing was clean throughout.** MiniMax M3 `:free` succeeded on every batch, with one transient `Retry-After: 60` wait-and-retry on the Proofpoint triage (decision 0038 working as intended). No batch failed, no `api_failures > 0`, no `NEEDS_MORE_DETAIL` left behind for OpenAI/Stripe.

### Phase 2 — Safe deletions, each preceded by a verified-unused grep

The following were removed because grep against `src/`, `tests/`, `scripts/`, `docs/` showed zero references outside the file itself and its own test (or the test was removed together):

Python modules (10):
- `src/research_agent/benchmark.py` + `tests/test_benchmark.py`
- `src/research_agent/company/validation.py` (with the two `validate_database` tests in `tests/test_import_master.py`)
- `src/research_agent/company/wave6.py` + `tests/test_wave5_assets.py` + `tests/test_wave6_assets.py` + `tests/test_wave6_selection.py`
- `src/research_agent/company/adapter_prioritization.py` + `tests/test_adapter_prioritization.py`
- `src/research_agent/pipeline/reclassify.py` (with the single `reclassify_current_jobs` test in `tests/test_lifecycle.py`)

Shell scripts (9):
- `scripts/final_audit.sh` (only referenced in `docs/TESTING.md` historical guidance)
- `scripts/_build_missing_core_rows.py`, `scripts/validate_master.py` (one-off helpers, no live callers)
- `scripts/run_ai_micro_canary.sh`, `scripts/run_network_canary.sh`, `scripts/run_p0_ai_resume.sh`, `scripts/run_p0_detail_followup.sh`, `scripts/run_p0_pilot.sh`, `scripts/run_stripe_greenhouse_probe.sh` (each a single V17–V23 step; V22+ operator path is `run_core_trial.sh` / `run_google_careers_probe.sh` / `prepare_tier_s_operational_sources.sh`)

CLI commands (9): `benchmark-taxonomy`, `validate-master`, `rank-adapter-candidates`, `prepare-wave6`, `finalize-wave6`, `reclassify-current`, `scan-official`, `prepare-canary-db`, `scan-canary`. `research-agent --help` now shows only the V2 surface.

### Deliberately NOT deleted (would change runtime behaviour)

- `src/research_agent/pipeline/filter.py` + `src/research_agent/filters/{cyber,geography,seniority}.py` are still wired into `pipeline/lifecycle.process_scan_results`, which is itself still wired into the LinkedIn CSV import (`sources/linkedin/importer.py`). Removing `VacancyFilter` would require inventing a neutral filter result; that refactor is out of scope for this conservative pass.
- `src/research_agent/pipeline/pilot.py` + `src/research_agent/cli.py scan-pilot` + `scripts/run_p0_core_expansion.sh` are still part of the current operator path (the user explicitly requested `scan-pilot` be retained).
- `scripts/run_google_careers_probe.sh`, `scripts/run_core_trial.sh`, `scripts/prepare_tier_s_operational_sources.sh`, `scripts/ensure_dashboard.sh`, `scripts/bootstrap_runtime_db.sh` are all retained as the V22+ operator path.
- `docs/decisions/*` and `TIER_S_ATS_MAPPING.md` retained per the user's instruction.

### Offline validation after Phase 2

- `uv run python -c "import research_agent; from research_agent.cli import app"` → `import_ok`.
- `uv run pytest -q` → **236 / 236 PASS** (test count after: −14 tests removed together with their source modules).
- `uv run ruff check src tests` → 90 pre-existing violations (one new F401 inherited from a deletion; non-blocking).
- `bash scripts/prepare_tier_s_operational_sources.sh` → V25.1 CORE_200 acceptance gate PASS; `tier_s_operational_sources_status: ok`.

### Quantitative cleanup

| Metric | Before | After | Delta |
|---|---:|---:|---:|
| Python files in `src/research_agent/` | 49 | 44 | −5 |
| Test files | 32 | 26 | −6 (7 legacy test files + 1 `reclassify` test + 2 `validate_database` tests) |
| Shell scripts in `scripts/` | 16 | 7 | −9 |
| CLI commands in `cli.py` | 33 | 24 | −9 |
| Lines of code in `src/research_agent/cli.py` | 1,890 | 1,384 | −506 |
| Lines of code in `src/` (rough, based on `wc -l`) | ~19,275 | ~16,500 | ~−2,800 |
| Pytest passed | 250 | 236 | −14 (legacy tests removed with their source modules) |
| Lint violations | 89 | 90 | +1 (one F401 from a deletion; non-blocking) |

### Known observations (NOT problems, recorded for the next task)

- The stale `https://job-boards.greenhouse.io/cloudhouse` portal row in the persistent runtime DB is preserved explicitly per decision 0052; not auto-cleaned.
- Workday listings produce no descriptions; the next V26 candidate is selective detail enrichment of those `NEEDS_MORE_DETAIL` rows (decision 0028).
- The dashboard's `job_summary` continues to count `CanonicalJob` (legacy V1 layer) rather than `SourceJob`; the raw-SQL smoke used in the report is correct, but the Streamlit tab shows 0 active jobs until/unless `CanonicalJob` is re-populated by `process_scan_results`. The V2.6 user-facing dashboard continues to read `SourceJob` via `source_job_rows`; this is unchanged.

### Next step (NOT implemented in this task)

After reviewing the smoke test log, the next milestone is **family-level controlled probing of the V25.1 `READY_TO_PROBE` queue** (62 employers, one ATS family at a time, starting with Greenhouse). Before that, an operator-driven, bounded Workday detail-enrichment run (decision 0028 + 0036) would close the most visible gap observed on Proofpoint. No new ATS adapters, no resolver, no scheduler, no Telegram.

STOP. Do not start the next step in this task.

## Update — 2026-09-04: V26.1 — Workday `/apply` detail path closure

A small, local product-wiring closure. No new architecture.

### What changed

- `pipeline/detail_enrichment.py`:
  - `_DETAIL_ADAPTERS = ("official_html", "workday")` — Workday rows now
    become detail candidates with the same CYBER / NEEDS_MORE_DETAIL /
    short-description policy as `official_html`.
  - `_detail_request_url(source_url, adapter)` and `_collapse_apply_path()`
    compute the actual detail fetch URL. For Workday this is
    `source_url + "/apply"`, idempotent against URLs that already end in
    `/apply`, and never double-appended.
  - `select_detail_candidates` accepts an optional `portal_ids` filter and
    runs the same-host check against the *actual* detail URL, not the
    raw source URL.
  - `enrich_official_html_details` plumbs the new `portal_ids` argument
    through to the candidate selector; the existing budget, pacing, and
    `parse_detail_html` / `_store_detail` paths are reused unchanged.
- `cli.py` (`enrich-details`):
  - New optional `--portal-id` (repeatable) flag. When omitted, the
    command behaves exactly as before.
- `dashboard/app.py`:
  - Top caption updated from
    "Local-first cybersecurity junior & internship research dashboard" to a
    V2-coherent description that explicitly mentions every seniority.
- `README.md`:
  - "Network safety" section now states the persisted default
    `global_concurrency=8` and notes that controlled probes override
    it on the command line.
- `tests/test_detail_enrichment.py`: 9 new tests, including
  Workday candidate selection, `source_url → /apply` transform,
  no-double-`/apply`, same-host protection, `official_html` URL
  invariance, `--portal-id` filtering, and a JSON-LD parsing check
  using the existing `parse_detail_html`.

### What did NOT change

- The CYBER semantic contract, the LLM routing, the V25.1 control plane,
  the persistent runtime DB, the dashboard tab list, the `--include-disabled`
  flag on `scan-discover`, and the `2000-01-01` sentinel for unknown
  verification dates are all untouched in this task.
- The 89 pre-existing ruff violations were left alone; the only new
  violations introduced by V26.1 were fixed (back to the 89 baseline).

### End-to-end live test on NVIDIA

`/apply` is confirmed consistent across three Workday tenants
(NVIDIA, CrowdStrike, Proofpoint — all 200 OK, JSON-LD `JobPosting`
present, description 4,355 / 8,818 / 7,495 characters respectively,
same-host in all three cases).

A live E2E on NVIDIA portal 539 produced this sequence in
`output/test_runs/workday_enrich_v261_20260904-110109.log`:

```
scan-discover --portal-id 539 --include-disabled
  → 15 jobs persisted (PENDING_AI, 0/15 descrizioni)
triage-pending --portal-id 539 --limit 20
  → 14 obvious_non_cyber + 1 candidate
analyze-pending --portal-id 539 --limit 20
  → 1 NEEDS_MORE_DETAIL (job 659, Senior ML Engineer, AI Safety)
enrich-details --portal-id 539 --limit 5
  → 2 request (robots.txt + /apply), 200 OK,
    description_chars=5597, parser=json_ld_jobposting,
    detail_url=...JR2024679/apply, PENDING_AI (re-queue)
analyze-pending --portal-id 539 --limit 5
  → 1 CYBER (cyber=True, needs_more=False)
```

Total request budget consumed: 2 HTTPS + 3 LLM calls. No retries, no
cooldowns triggered. The re-analysis with the real 5.6KB description
re-classified the job as CYBER with `needs_more=False` and persisted
a `JobAiAnalysis` row.

### Quantitative summary

| Metric | Before V26.1 | After V26.1 |
|---|---:|---:|
| Pytest passed | 254 | 263 (+9 new) |
| Ruff violations | 89 | 89 (no new) |
| CLI commands in `cli.py` | 24 | 24 |
| New files | — | 0 |
| Files modified | — | 3 (`detail_enrichment.py`, `cli.py`, `app.py`, `README.md`) |
| Lines added in `detail_enrichment.py` | — | ~30 |
| New tests | — | 9 (all in `test_detail_enrichment.py`) |

### Suggested next test (do not implement here)

A bounded Workday detail-enrichment run over the existing CORE_200
Workday portals (NVIDIA 539, Proofpoint 265, Crowdstrike 138, PayPal
514, Intel 521, etc.) — i.e. a `--portal-id 539,265,138,514,521`
operator action over the persistent runtime DB, with a small
`--limit` per portal, then a single `analyze-pending` covering all
five. The expected outcome is a meaningful increase in
`detail_description_nonempty` and a lower `NEEDS_MORE_DETAIL` count
without any new architecture.
