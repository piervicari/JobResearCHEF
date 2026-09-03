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
