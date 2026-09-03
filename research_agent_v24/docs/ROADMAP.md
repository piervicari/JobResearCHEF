# Execution roadmap

Updated: 2026-09-01

This is the ordered delivery plan for moving the verified local MVP to a useful, repeatable research
tool. Work advances only when the preceding safety or quality gate passes. Historical reports remain
immutable evidence; current state is recorded in `STATUS.md`.

## Completion rules

- Network expansion stops on a failed cohort gate, any `429`, access-control challenge, unexpected
  complete empty snapshot, or unexplained lifecycle change.
- The authoritative master v1.5 is never overwritten. Corrections and new waves are versioned and
  synchronized while preserving job history and provenance.
- Adapter support requires an observed public contract, sanitized fixture, offline contract tests and
  a bounded canary. An ATS label alone is not evidence.
- Taxonomy changes require a before/after benchmark report. Ambiguous cases remain `REVIEW`.
- A work package is complete only when code, tests, documentation and persisted evidence agree.

## Ordered work packages

### 0. Durable baseline

- [x] Run the full offline suite, Ruff, master validation and taxonomy benchmark.
- [x] Verify that databases, caches, backups, environment files and local artifacts are ignored.
- [x] Create the first reviewed Git commit.

Evidence: commit `a2c75be`; 121 tests, Ruff, master validation and taxonomy benchmark passed.

### 1. Anti-blocking and local operations hardening

- [x] Add explicit request budgets per host and per run, including paginated adapters.
- [x] Add a host circuit breaker for `401`, `403`, `429`, robots denial and detected challenges.
- [x] Persist a cooldown so a blocked host is not retried by the next accidental cohort.
- [x] Make the User-Agent operator contact configurable. The original hard requirement was later
  relaxed by product decision 0017; contact is optional while the User-Agent remains stable.
- [x] Add a backup-retention command with dry-run default, integrity protection and documented policy.
- [x] Cover all controls with offline tests and expose their outcomes in run evidence.

Gate: full offline verification passes and a simulated blocked host cannot receive further requests.

### 2. Versioned registry corrections and synchronization

- [x] Define a correction/wave artifact schema with action, old value, new value, evidence, date and
  reason.
- [x] Implement validation for duplicate clusters, incomplete evidence, in-place master mutation and
  unsafe URLs.
- [x] Implement a synchronizing import that preserves prior import batches, cluster identity, portal
  history, source jobs and canonical jobs.
- [x] Support explicit `UPDATE`, `RETIRE` and new-resolution actions without destructive replacement.
- [x] Produce machine-readable and human-readable audit reports.

Gate: fixture-led tests prove idempotency, history preservation, rollback-by-batch visibility and
exact acceptance metrics.

### 3. Remediate run 17 and repeat progressive rollout

- [x] Re-resolve or retire the stale DNS routes for Brunello Cucinelli, Centrica and Iveco Group.
- [x] Re-resolve or retire the Equinix `404` route.
- [x] Mark Check Point and Leidos as robots-denied unless a separate public official contract exists.
- [x] Mark Caterpillar, Mimecast, PayPal and ServiceNow as access-denied unless a separate public
  official contract exists.
- [x] Apply the changes through the versioned registry workflow, never by editing v1.5 in place.
- [x] Repeat the same representative 50-portal cohort.
- [x] Proceed to a representative 100-portal cohort only after the 50-portal gate passes.

Gate: failure rate is at most 10%, retries at most 20%, zero `429`, zero unexpected complete empty
snapshots and zero unexplained closures.

Evidence: runs 22 and 26 pass. Run 26 completed at 8% failure, 0% retry, zero `429` and zero
unexpected complete empty snapshots. See `docs/reports/scan_scale_validation_v1.md`.

### 4. Representative taxonomy benchmark

- [x] Expand the labeled benchmark from 46 to at least 200 cases.
- [x] Stratify by ATS, cyber category, seniority, geography, remote ambiguity, generic-SWE negatives,
  vendor boilerplate and hard negative titles.
- [x] Record label provenance and a short rationale for every non-obvious case.
- [x] Report component accuracy plus final precision and recall, not accuracy alone.
- [x] Preserve the existing cases as regression anchors.

Gate: at least 200 valid cases and the configured 95% component/final threshold passes.

Evidence: `data/benchmarks/taxonomy_v1.csv`, `docs/reports/taxonomy_benchmark.md` and
`docs/reports/taxonomy_benchmark_design_v1.md`. The 200-case gate passes.

### 5. Filtering and company identity improvements

- [x] Add deterministic experience parsing for observed `0-2/3 years` and ordinal-level cases.
- [x] Distinguish unknown structured country from known out-of-scope geography.
- [x] Consume richer structured location fields where supported before adding aliases.
- [x] Add company aliases with provenance and `PROPOSED`/`VERIFIED` status.
- [x] Allow fuzzy matching to propose candidates only; it must never write a cluster automatically.
- [x] Reclassify stored observations offline and publish benchmark deltas.

Gate: benchmark remains above threshold, no regression anchor changes silently, and all automatic
company mappings are supported by verified aliases or exact unambiguous normalization.

Evidence: 212-case benchmark PASS, 151 tests, run 27 and
`docs/reports/filter_improvements_v1.md`.

### 6. Operator dashboard and review workflow

- [x] Show lifecycle confidence (`complete`/`incomplete`) for each job and source.
- [x] Add an actionable review queue with filter reasons and ambiguity signals.
- [x] Show per-portal warnings, latest attempt error, cooldown and circuit-breaker state.
- [x] Distinguish stale route, robots denial, access denial, schema drift and transient failure.
- [x] Add coverage views by structured adapter, health and high-value unresolved cluster.
- [x] Expose the handover's minimum analytics: current/recent jobs, country/company/category/
  seniority/workplace/source breakdowns, geography/sector/ATS coverage, complete per-run HTTP and
  anomaly diagnostics, and filters for company, keyword, discovery age, workplace and lifecycle.
- [x] Add dashboard tests and a rendered smoke verification.

Gate: an operator can explain every `REVIEW`, failed portal and non-closure from the dashboard without
querying SQLite manually.

Evidence: `docs/reports/dashboard_validation_v1.md` and
`docs/reports/dashboard_analytics_validation_v2.md`; 169-test offline suite and rendered localhost
smoke PASS with no console errors.

### 7. Evidence-driven adapter expansion

- [x] Rank the 398 fallback portals by employer value, likely junior/cyber yield, shared-host leverage
  and observed public contract.
- [x] Add adapters only for the highest-value verified families or site-specific public contracts.
- [x] For each adapter add sanitized fixtures, pagination/schema/error/budget tests and a bounded live
  canary.
- [x] Promote lifecycle completeness only when the adapter proves a complete snapshot.

Gate: every routing increase is reviewed, contract-backed and improves complete coverage without
weakening access controls.

Evidence: `docs/reports/fallback_adapter_priority_v1.csv`,
`docs/reports/radancy_adapter_rollout_v1.md`, runs 28-29 and ADR 0012.

### 8. Prioritized Wave 6

- [x] Select 100-200 unresolved clusters using a reproducible score: employer scale, cybersecurity
  relevance, target geography, early-career probability, cluster record count and likely ATS quality.
- [x] Resolve only official corporate, careers and job-search endpoints with evidence.
- [x] Preserve ambiguous cases as deferred; never force a parent or same-name match.
- [x] Produce the wave CSV, mapping audit, summary JSON, synchronized master and distributable ZIP.
- [x] Validate exact row/cluster counts, uniqueness, evidence completeness and prior-wave immutability.

Gate: all Wave 6 validation checks pass and the synchronized database preserves historical jobs.

Evidence: 100 uniquely ranked clusters, 15 official resolutions, 85 explicit deferrals, master v1.10,
`docs/reports/portal_resolution_wave6.md` and the deterministic Wave 6 distribution ZIP. The v1.5
checksum and all 12,503 source rows remain unchanged.

### 9. Source operation and final hardening

- [x] Gate the manual LinkedIn production exercise on a reviewed operator-supplied CSV. None was
  available, so the strict import and cross-source dedup contracts were verified offline and the
  production-only duplicate measurement was recorded as an external-data contingency.
- [x] Establish a conservative scan cadence only after the 100-portal cohort passes.
- [x] Add CI for the offline suite, immutable artifact reconstruction and recovery validation.
- [x] Review the migration trigger. It is not met: the schema remains within the documented additive
  bootstrap, so formal migrations are required before the first non-additive change rather than now.
- [x] Review the persistence/execution trigger. Measured volume and single-operator concurrency still
  support SQLite and manual/local execution.
- [x] Run and document a final end-to-end audit covering import, scan, classification, deduplication,
  lifecycle, dashboard, backup and recovery.

Gate: all applicable checks pass from a clean checkout, operational recovery is demonstrated and no
P0/P1 item remains open. Production LinkedIn ingestion remains contingent on the operator supplying
reviewed public data; authenticated scraping is never a substitute.

Evidence: `.github/workflows/ci.yml`, `scripts/final_audit.sh`,
`docs/reports/source_operation_final_hardening_v1.md`,
`docs/reports/final_end_to_end_audit_v2.md` and `docs/reports/recovery_validation_v1.md`. The latest
clean audit passed 169 tests, reconstructed master v1.10 from the immutable v1.5 plus all versioned batches,
and proved an exact-checksum recovery. The original handover Definition of Done is audited 18/18 PASS
in `docs/reports/mvp_definition_of_done_audit_v1.md`. No P0/P1 item remains open.

## Explicit non-goals

- Authenticated LinkedIn scraping, CAPTCHA bypass, proxy rotation or access-control evasion.
- Browser automation as a generic fallback.
- Per-master-row scanning, automatic fuzzy company assignment or LLM-controlled inclusion.
- People research, CV-fit scoring, generic SWE, senior roles or Middle East expansion.
- Cloud, microservices, Postgres or distributed scheduling without a measured need.
