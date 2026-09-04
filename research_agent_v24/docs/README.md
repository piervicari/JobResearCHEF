# Documentation

Start with [`CODEX_HANDOVER_CURRENT.md`](CODEX_HANDOVER_CURRENT.md) for the cumulative current-state handover.

# Documentation index

This directory is the engineering source of truth for the research agent. Documentation must be
updated in the same change as any behavior, configuration, data contract or operational procedure
that it describes.

## Start here

- [`../README.md`](../README.md): product scope, setup and common commands.
- [`CODEX_HANDOVER_CURRENT.md`](CODEX_HANDOVER_CURRENT.md): cumulative current-state handover.
- [`ROADMAP_V2.md`](ROADMAP_V2.md): current product roadmap.
- [`OPERATIONS.md`](OPERATIONS.md): safe local operation, backups, scan gates and recovery.
- [`TESTING.md`](TESTING.md): test layers, offline guarantees and release verification.
- [`../SECURITY.md`](../SECURITY.md): trust boundaries, vulnerability reporting and known risks.
- [`../CONTRIBUTING.md`](../CONTRIBUTING.md): development workflow and definition of done.

## Design and decisions

- [`architecture/`](architecture/): accepted Architecture Decision Records (ADRs). Add an ADR when
  changing a trust boundary, persistence invariant, external-source contract or irreversible design
  choice.
- [`decisions/`](decisions/): product/design decisions agreed for the target system, including
  decisions not yet implemented. Each record includes rationale, implementation shape, trade-offs and
  migration status.

## Evidence

- [`reports/`](reports/): generated or audited validation evidence. Reports describe a particular
  run or dataset snapshot; they are not a substitute for current runtime checks.
- [`reports/final_end_to_end_audit_v2.md`](reports/final_end_to_end_audit_v2.md): latest clean-database
  reconstruction, acceptance, dashboard and recovery audit.
- [`reports/dashboard_analytics_validation_v2.md`](reports/dashboard_analytics_validation_v2.md):
  query, filter and rendered-browser evidence for the complete handover analytics.
- [`reports/source_operation_final_hardening_v1.md`](reports/source_operation_final_hardening_v1.md):
  source cadence, LinkedIn contingency and architecture-trigger decisions.

## Documentation lifecycle

Every document should state facts that can be verified from code, configuration or a named report.
Use `CODEX_HANDOVER_CURRENT.md` for current facts, ADRs for decisions and consequences, and
`OPERATIONS.md` for procedures. Do not silently rewrite historical reports after behavior changes;
create a new report or clearly record its regeneration date and inputs.


## Current product roadmap

Use [`ROADMAP_V2.md`](ROADMAP_V2.md) for the current cyber-pilot direction. Historical evidence of
the completed deterministic-filtering MVP lives in `docs/reports/` and `docs/architecture/`.

## V2 current path

- [`ROADMAP_V2.md`](ROADMAP_V2.md) — current product roadmap.
- [`CODEX_HANDOVER_CURRENT.md`](CODEX_HANDOVER_CURRENT.md) — cumulative state for the next coding
  agent.
- [`decisions/`](decisions/) — versioned product/implementation decisions.
