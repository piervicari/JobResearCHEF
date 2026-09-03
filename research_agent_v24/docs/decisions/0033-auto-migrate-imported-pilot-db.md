# 0033 — Auto-migrate imported pilot databases

- **Date:** 2026-09-02
- **Status:** ACCEPTED

## Context

The first V16 selective-detail follow-up successfully imported the prior P0 pilot database, but then failed locally before any network or LLM work with:

`sqlite3.OperationalError: no such column: source_jobs.detail_title`

The imported database was produced by the earlier P0 pilot before the selective-detail-enrichment fields existed. The application models in V16 expected the new `detail_*` columns, while the copied SQLite file still had the older schema.

## Decision

Every imported pilot DB must be upgraded **offline and additively immediately after copy** using the project's existing schema bootstrap:

`research-agent init-db --database-url sqlite:///data/pilot/research_agent_pilot.db`

The bootstrap script prints `schema_migration: ok` only after that step succeeds.

## Why

- Preserve the 36 already-discovered pilot jobs and their AI analyses.
- Avoid repeating career-site traffic or LLM calls merely because code/schema advanced.
- Reuse the additive SQLite migration mechanism that already exists in `db/migrations.py` rather than inventing a second migration path.
- Make cross-version pilot DB reuse explicit and fail-fast.

## Implementation implications

- `scripts/bootstrap_latest_pilot_db.sh` copies the previous pilot DB, then runs the schema bootstrap before returning success.
- The migration is idempotent: already-current databases remain unchanged.
- During the current additive-only MVP phase, missing columns are added with safe defaults; no destructive migration is performed.

## Trade-offs

This remains a lightweight MVP migration system rather than a fully versioned migration framework such as Alembic. That is intentional while schema changes are additive-only. Introduce a formal migration framework only when destructive/transformative migrations become necessary.
