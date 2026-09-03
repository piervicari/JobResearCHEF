# ADR 0010: Versioned registry changes with immutable before/after audit

- Status: Accepted
- Date: 2026-08-31

## Context

The authoritative master v1.5 is intentionally immutable, but live evidence can prove that a jobs
route is stale, retired or replaced. Wave 6 must also add resolutions without detaching historical
source jobs from the portal used when they were observed.

## Decision

- Accept strict CSV artifacts containing one `ADD`, `UPDATE`, `RETIRE`, `SUSPEND` or `RESUME` action per corporate
  cluster.
- Require old-URL matching for updates and retirements plus evidence URL, verification date and
  reason for every action.
- Record each artifact as an immutable checksum-idempotent import batch.
- Store immutable before/after JSON in `registry_change_audit`.
- Preserve old `Portal` rows and their source-job relationships; deactivate a portal only when no
  current cluster mapping uses it.
- Keep access-denied or robots-denied mappings resolved but exclude their portals from automatic
  cohorts until a reviewed `RESUME` action is applied.
- Update current company resolution columns and export a new synchronized master without changing
  the original v1.5 file.
- Refuse overwriting a synchronized master artifact.

## Consequences

Current registry state can evolve while historical jobs and evidence remain explainable. Retired
portals still occupy database rows and must be excluded by `active_in_registry` in operational
counts. A change artifact with an incorrect old URL fails atomically instead of overwriting a newer
resolution.
