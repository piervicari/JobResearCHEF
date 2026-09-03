# Source operation and final hardening

Date: 2026-08-31

## Result

Package 9 is complete for every applicable input. Bounded official-source operation has a manual
cadence and explicit stop conditions, the offline verification path is encoded in CI, recovery is
exercised, and the current data volume does not trigger a persistence or migration redesign. No
authenticated source access or access-control bypass was introduced.

## LinkedIn production contingency

No reviewed operator-supplied production LinkedIn CSV was present. A production duplicate-rate
number would therefore be fabricated and was not reported. This is an external-data contingency, not
a scanner failure.

The available contract is nevertheless covered offline: the importer rejects incorrect schemas,
extracts a job ID conservatively, is checksum-idempotent, adds no portal, preserves
`linkedin_manual` provenance, enters the same deterministic classification/dedup pipeline and has a
cross-source canonical-apply-URL test. When a reviewed CSV is supplied, the operator can run
`ingest-linkedin-csv` and report official-only, LinkedIn-only and cross-source matches without any
login automation.

## Official-source cadence

The representative 100-portal gate passed before a recurring cadence was defined. The runbook now
sets 5-10 canaries per session, explicit cohorts of at most 50, at most two structured sessions and
one fallback session per week, no deliberate same-host selection more than once per day, and no
unattended `--all`. Runtime limits remain 30 requests per host and 500 per run.

Any `429`, access challenge, authentication/CAPTCHA response, robots denial, failed gate, unexpected
complete empty snapshot or unexplained lifecycle change stops expansion. This materially reduces the
risk of rate limiting or blocking, but no client can guarantee that a third-party service will not
change or withdraw public access.

## Architecture trigger review

- **Formal migrations:** not triggered. Changes remain additive and reproducible through bootstrap.
  Introduce a migration framework before the first non-additive transform, rollback requirement or
  multi-version deployment.
- **SQLite:** retained. The current database has 12,503 company records, 5,789 source jobs and 108
  canonical jobs under one local operator. There is no measured concurrent-write need.
- **Manual/local execution:** retained. No scheduler is required for the conservative reviewed
  cadence. Reconsider only after measured missed-run, concurrency or operational-load evidence.

## Operations evidence

- Clean disposable-database audit: PASS, documented in `final_end_to_end_audit_v1.md`.
- Recovery of the current database backup: exact SHA-256, integrity and per-table counts PASS.
- Retention: an exact dry-run was reviewed before applying `--keep-last 3`; 19 old databases and two
  associated sidecars were removed, 1,089,814,528 bytes reclaimed and the three newest verified
  backups retained.
