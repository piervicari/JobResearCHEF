# Documentation

Start with [`CODEX_HANDOVER_CURRENT.md`](CODEX_HANDOVER_CURRENT.md) for the current state (its top `CURRENT SNAPSHOT — 2026-09-07` section overrides all dated sections below it). Repository ownership and tree: [`REPOSITORY_LAYOUT.md`](REPOSITORY_LAYOUT.md).

# Documentation index

This directory is the engineering source of truth for the research agent. Documentation must be
updated in the same change as any behavior, configuration, data contract or operational procedure
that it describes.

## Start here

- [`../README.md`](../README.md): product scope, setup and common commands.
- [`CODEX_HANDOVER_CURRENT.md`](CODEX_HANDOVER_CURRENT.md): current state for the next coding agent.
- [`REPOSITORY_LAYOUT.md`](REPOSITORY_LAYOUT.md): repository ownership/tree (production vs evidence vs prototype).
- [`ROADMAP_V2.md`](ROADMAP_V2.md): forward plan (CURRENT section on top wins over older sequencing).
- [`OPERATIONS.md`](OPERATIONS.md): safe local operation, backups, scan gates and recovery.
- [`TESTING.md`](TESTING.md): test layers, offline guarantees and release verification.
- [`../SECURITY.md`](../SECURITY.md): trust boundaries, vulnerability reporting and known risks.
- [`../CONTRIBUTING.md`](../CONTRIBUTING.md): development workflow and definition of done.

## Design and decisions

- [`decisions/`](decisions/): AGREED TARGET/PRODUCT/IMPLEMENTATION decisions (log 0001–0060, index in `decisions/README.md`), including decisions not yet implemented. Each record includes rationale, implementation shape, trade-offs and migration status.
- [`architecture/`](architecture/): architecture decisions describing the CURRENT/IMPLEMENTED system unless explicitly marked otherwise. Older implemented-system ADRs; do not confuse with the forward-looking `decisions/` log. Not merged with `decisions/` in this task.

## Evidence

- [`reports/`](reports/): IMMUTABLE empirical evidence. Reports describe a particular
  run or dataset snapshot; they are not a substitute for current runtime checks. Never silently rewrite a report — add a new dated one.
- [`reports/final_end_to_end_audit_v2.md`](reports/final_end_to_end_audit_v2.md): latest clean-database
  reconstruction, acceptance, dashboard and recovery audit.
- [`reports/dashboard_analytics_validation_v2.md`](reports/dashboard_analytics_validation_v2.md):
  query, filter and rendered-browser evidence for the complete handover analytics.
- [`reports/source_operation_final_hardening_v1.md`](reports/source_operation_final_hardening_v1.md):
  source cadence, LinkedIn contingency and architecture-trigger decisions.

## Historical standalone docs (kept in place — referenced, do not move)

- [`STATUS.md`](STATUS.md): early status snapshot; kept because `CONTRIBUTING.md`, the handover and `ROADMAP.md` reference it. Historical.
- [`ROADMAP.md`](ROADMAP.md): original deterministic-filtering MVP roadmap; superseded in product direction by `ROADMAP_V2.md`. Historical.
- [`V2_IMPLEMENTATION_STATUS.md`](V2_IMPLEMENTATION_STATUS.md): cumulative V2 status log; superseded as current state by `CODEX_HANDOVER_CURRENT.md`. Historical.
- [`LIVE_CANARY_TEST_PLAN.md`](LIVE_CANARY_TEST_PLAN.md): staged canary policy (decision 0013); referenced by `ROADMAP_V2.md`. Historical plan, normative policy lives in the ADR.
- [`CANARY_RESULTS_2026-09-02.md`](CANARY_RESULTS_2026-09-02.md): dated canary results. Historical evidence.
- [`LLM_ROUTING_BENCHMARK_2026-09-02.md`](LLM_ROUTING_BENCHMARK_2026-09-02.md): dated routing benchmark cited by decision 0016. Historical evidence.

## Archive

- [`archive/`](archive/): retired docs with zero repository references (`AI_MICRO_CANARY.md`, `CRITICAL_ANALYSIS.md`, `V2_QUICKSTART.md`).
- [`archive/handovers/`](archive/handovers/): retired handover (`CODEX_HANDOVER_RESEARCH_AGENT_PIER.md`, pre-V2 milestone). The current handover is `CODEX_HANDOVER_CURRENT.md`, not this.

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
