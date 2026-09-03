# Product Decision Log

This directory records product and implementation decisions agreed during design discussions.
It is intentionally separate from `docs/architecture/`:

- `docs/decisions/` = agreed target behavior, including decisions that may not yet be implemented.
- `docs/architecture/` = architecture decisions describing the current/implemented system unless explicitly marked otherwise.
- `docs/reports/` = evidence from a particular run or dataset snapshot.

## Rule

Every material decision should record:

1. status;
2. decision;
3. rationale;
4. implementation implications / schema;
5. trade-offs and rejected alternatives;
6. relationship to the current implementation;
7. open questions.

A decision can be `Proposed`, `Accepted`, `Accepted principle / details TBD`, `Deferred`, or `Superseded`.
Do not silently rewrite historical decisions: supersede them explicitly.

## Current decisions

| ID | Decision | Status |
|---|---|---|
| [0001](0001-cyber-first-scope.md) | Cyber-first scope; all cyber seniorities retained | Accepted |
| [0002](0002-curated-company-universe-and-manual-tiers.md) | Human-curated target employers and manual tiers | Accepted |
| [0003](0003-portal-resolution-lite.md) | Simplified official career portal resolution | Accepted |
| [0004](0004-llm-semantic-job-analysis.md) | LLM owns semantic job interpretation; code owns mechanics | Accepted |
| [0005](0005-job-storage-and-ai-analysis-contract.md) | Store complete cyber job records; keep AI analysis separate | Accepted |
| [0006](0006-job-identity-lifecycle-and-closure.md) | Reliable job identity, sightings, and conservative closure | Accepted |
| [0007](0007-internship-program-intelligence.md) | Evidence-backed internship/program research module | Deferred after usable cyber scanner |
| [0008](0008-linkedin-boundary.md) | LinkedIn automation removed from critical path | Accepted |
| [0009](0009-tiered-scan-cadence.md) | Higher tiers scanned more frequently | Superseded operationally by 0011 |
| [0010](0010-initial-target-employer-set-v0-1.md) | Initial curated set and target-first portal resolution | Superseded by accepted pilot set v0.2 |
| [0011](0011-core-target-membership-vs-scan-cadence.md) | 200-employer core membership separated from scan cadence | Accepted |
| [0012](0012-job-identity-payload-and-location-variants.md) | Job identity separated from canonical payload/content versioning | Accepted + implemented in V2 ingestion |
| [0013](0013-low-impact-live-canary-scanning.md) | Staged low-impact live canary policy before core rollout | Accepted + implemented |
| [0014](0014-sourcejob-as-v2-discovery-queue.md) | SourceJob reused as durable V2 discovery/Pending-AI queue | Accepted + implemented |
| [0015](0015-jobanalyzer-structured-batch-provider-contract.md) | Structured batch JobAnalyzer and strict provider contract | Partially superseded by 0016 |
| [0016](0016-task-difficulty-and-fallback-llm-routing.md) | Difficulty-based task lanes + quality-aware Google/OpenRouter fallback | Accepted + implemented |
| [0017](0017-preflight-safety-and-optional-operator-contact.md) | Dry-run preflight safety, optional operator contact, and migrated V2 baseline | Accepted + implemented |
| [0018](0018-canary-progression-one-host-at-a-time.md) | Progress live canaries one host at a time | Accepted + implemented |
| [0019](0019-network-health-vs-discovery-health-and-ai-micro-canary.md) | Separate network/access health from extraction health; isolate first AI test | Accepted + implemented |
| [0020](0020-live-llm-progress-bounded-timeouts-and-medium-fast-fallback.md) | Live LLM progress, bounded timeouts, fast MEDIUM fallback | Partially superseded by 0021 |
| [0021](0021-free-only-llm-routing.md) | Free-only LLM routing; no paid OpenRouter fallback | Accepted + implemented; timeout values superseded by 0022 |
| [0022](0022-five-minute-free-llm-attempt-timeouts.md) | Five-minute per-attempt timeouts for free LLM calls | Accepted + implemented |
| [0023](0023-temporarily-disable-gemini-3-7-and-log-test-runs.md) | Temporarily disable Gemini 3.7 Flash; persist test output to files | Accepted + implemented |
| [0024](0024-persistent-user-secrets-across-zip-versions.md) | Persistent per-user API secrets across downloaded ZIP versions | Accepted + implemented |
| [0025](0025-first-p0-end-to-end-pilot-cohort.md) | Five-employer low-impact P0 end-to-end pilot | Accepted + implemented |
| [0026](0026-ai-micro-canary-accepted-proceed-to-p0-pilot.md) | Accept the five-job AI micro-canary and proceed to end-to-end P0 pilot | Accepted |
| [0027](0027-p0-end-to-end-pilot-accepted-with-data-quality-gates.md) | Accept P0 pilot; gate scale-out on parser/detail quality | Accepted |
| [0028](0028-selective-detail-enrichment-after-first-ai-pass.md) | Selective second-stage detail enrichment for AI-relevant jobs | Accepted + implemented baseline |
| [0029](0029-trellix-workday-registry-correction-and-generic-navigation-links.md) | Correct Trellix to Workday; navigation links are not vacancies | Accepted + implemented |
| [0030](0030-latest-ai-result-view-is-one-row-per-source-job.md) | Operational AI views show latest analysis per source job | Accepted + implemented |
| [0031](0031-defer-ai-for-security-vs-security-of-ai-taxonomy.md) | Distinguish AI-for-Security vs Security-of-AI only during future AI/SWE expansion | Deferred P3 |
| [0032](0032-use-project-python-via-uv-in-operational-scripts.md) | Use project Python via uv in operational scripts | Accepted + implemented |
| [0033](0033-auto-migrate-imported-pilot-db.md) | Auto-migrate imported pilot DBs before querying new schema | Accepted + implemented |
| [0034](0034-turnstile-widget-is-not-a-hard-access-challenge.md) | Embedded Turnstile widgets do not imply page-level access challenge | Accepted + implemented |
| [0035](0035-substantive-descriptions-require-binary-cyber-decision.md) | Substantive descriptions require CYBER/NON_CYBER decision | Accepted + implemented |
| [0036](0036-detail-enrichment-per-host-safety-cap.md) | Bound selective detail fetches per host | Accepted + implemented |
| [0037](0037-effective-ai-input-hash-and-idempotent-analysis-persistence.md) | Effective AI input hash + idempotent AI persistence | Accepted + implemented |
| [0038](0038-minimax-first-retry-after-aware-free-routing.md) | MiniMax-first free routing with bounded Retry-After-aware retry | Accepted + implemented |
| [0039](0039-ai-batch-failures-return-nonzero-exit.md) | AI batch failures return non-zero process exit while preserving PENDING_AI | Accepted + implemented |
| [0040](0040-targeted-semantic-cleanup-instead-of-blanket-reanalysis.md) | Requeue only fully-described stale NEEDS_MORE_DETAIL rows after the v3 contract change | Accepted + implemented |
| [0041](0041-first-controlled-core-employer-expansion.md) | First controlled 10-employer core expansion after P0 validation | Accepted + implemented as operator runbook |

## Important migration note

The legacy `scan-official` / reclassification path still implements deterministic cyber/seniority/geography filtering as described in `docs/architecture/0005-deterministic-filtering-and-reclassification.md`. V2 now provides `scan-discover`, which persists source truth as `PENDING_AI` without applying those semantic filters. The remaining P0 migration is the JobAnalyzer + cyber product view/promotion path; legacy commands remain for historical compatibility and must not be used as the V2 product path.
- [0042 — Persistent runtime database across code versions](0042-persistent-runtime-database-across-code-versions.md)
- [0043 — Dashboard supervisor and one-command core trial](0043-dashboard-supervisor-and-one-command-core-trial.md)
- [0044 — Canonical careers URL vs operational ATS source](0044-canonical-careers-url-vs-operational-ats-source.md)
- [0045 — Network budget is not a record budget for one-shot catalogs](0045-network-budget-is-not-a-record-budget-for-one-shot-catalogs.md)
- [0046 — Large-batch high-recall LLM triage before full analysis](0046-large-batch-high-recall-llm-triage-before-full-analysis.md)
- [0047 — One-employer probes with web ground-truth checks](0047-one-employer-probes-with-web-ground-truth-checks.md)

- [0048 — Narrow CYBER boundary excludes financial crime and generic risk/compliance](0048-narrow-cyber-boundary-excludes-financial-crime-and-generic-risk.md)
- [0049 — Google Careers uses its anonymous structured batchexecute RPC](0049-google-careers-anonymous-structured-rpc-adapter.md)
- [0050 — Google full-catalog network budget is probe-scoped, not global](0050-google-full-catalog-budget-is-probe-scoped-not-global.md)