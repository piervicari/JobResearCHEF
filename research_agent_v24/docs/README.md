# Documentation

Start with [`CODEX_HANDOVER_CURRENT.md`](CODEX_HANDOVER_CURRENT.md) for the cumulative current-state handover.

# Documentation index

This directory is the engineering source of truth for the research agent. Documentation must be
updated in the same change as any behavior, configuration, data contract or operational procedure
that it describes.

## Start here

- [`../README.md`](../README.md): product scope, setup and common commands.
- [`STATUS.md`](STATUS.md): verified implementation state and current milestone.
- [`ROADMAP.md`](ROADMAP.md): ordered execution plan and completion gates.
- [`OPERATIONS.md`](OPERATIONS.md): safe local operation, backups, scan gates and recovery.
- [`TESTING.md`](TESTING.md): test layers, offline guarantees and release verification.
- [`../SECURITY.md`](../SECURITY.md): trust boundaries, vulnerability reporting and known risks.
- [`../CONTRIBUTING.md`](../CONTRIBUTING.md): development workflow and definition of done.

## Design and decisions

- [`CRITICAL_ANALYSIS.md`](CRITICAL_ANALYSIS.md): prioritized gaps and work that should not be done
  yet.
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
- [`reports/mvp_definition_of_done_audit_v1.md`](reports/mvp_definition_of_done_audit_v1.md): explicit
  18/18 reconciliation against the original MVP Definition of Done.
- [`reports/source_operation_final_hardening_v1.md`](reports/source_operation_final_hardening_v1.md):
  source cadence, LinkedIn contingency and architecture-trigger decisions.

## Documentation lifecycle

Every document should state facts that can be verified from code, configuration or a named report.
Use `STATUS.md` for current facts, ADRs for decisions and consequences, and `OPERATIONS.md` for
procedures. Do not silently rewrite historical reports after behavior changes; create a new report
or clearly record its regeneration date and inputs.


## Current product roadmap

Use [`ROADMAP_V2.md`](ROADMAP_V2.md) for the current cyber-pilot direction. `ROADMAP.md` is retained as historical evidence of the completed deterministic-filtering MVP.

## V2 current path

- [`ROADMAP_V2.md`](ROADMAP_V2.md) — current product roadmap.
- [`V2_IMPLEMENTATION_STATUS.md`](V2_IMPLEMENTATION_STATUS.md) — what is implemented vs still pending.
- [`V2_QUICKSTART.md`](V2_QUICKSTART.md) — safe operational sequence.
- [`LIVE_CANARY_TEST_PLAN.md`](LIVE_CANARY_TEST_PLAN.md) — low-impact network canary policy.
- [`decisions/`](decisions/) — versioned product/implementation decisions.

- [`LLM_ROUTING_BENCHMARK_2026-09-02.md`](LLM_ROUTING_BENCHMARK_2026-09-02.md) — benchmark basis and task-difficulty model assignments for the routed JobAnalyzer.
