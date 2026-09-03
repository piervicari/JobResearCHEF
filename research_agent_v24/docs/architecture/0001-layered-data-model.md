# ADR 0001: Separate company, portal and vacancy layers

- Status: Accepted
- Date: 2026-08-30

## Context

The company master changes slowly, portal resolution changes occasionally and job observations
change on every scan. Treating a master row as a scan target would produce duplicate requests and
couple discovery to vacancy collection.

## Decision

The relational model has three separate layers:

1. `CompanyRecord` preserves every source row and its raw JSON.
2. `CorporateCluster` is the stable company identity used before any network work.
3. `Portal` is a deduplicated operational Jobs Search URL. `ClusterPortalMapping` preserves all
   company-specific resolution metadata and provenance.
4. `SourceJob` stores observations; `CanonicalJob` stores cross-source deduplicated vacancies.

Current scan fan-out is therefore 510 portals, not 1,263 covered rows or 12,503 master rows.

## Consequences

- Shared portals are fetched once per run.
- Conflicting metadata is not silently collapsed.
- Source observations can retain LinkedIn and official-portal provenance while sharing one
  canonical job.
- Portal resolution and recurring job scans remain independently evolvable.

