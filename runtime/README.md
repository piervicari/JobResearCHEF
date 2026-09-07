# runtime/ — NON-CANONICAL PROTOTYPE / REFERENCE AREA

> This directory is NOT the production runtime.
> The production runtime is `../research_agent_v24/src/research_agent/`.
> Do NOT implement production changes here.

## What this is

Historical evidence from the declarative SourceSpec prototype track:

- SourceSpec v0.1 schema, executor prototype, and HTTP bridge prototype
  (`source_spec.schema.json`, `job.schema.json`, `spec_executor.py`,
  `jobresearchchef_bridge.py` — the last two are symlinks to the canonical
  implementation under `../research_agent_v24/src/research_agent/sources/declarative/`);
- frozen catalog fixtures (`fixtures/`, `sources/`, `candidates/`);
- probe/validation scripts (`validate_specs.py`, `test_*batch*.py`,
  `test_spec_executor.py`, `test_jobresearchchef_bridge.py`);
- historical reports (`BATCH*_REPORT.md`, `SOURCE_SPEC_V0_REPORT.md`,
  `PHASE1_HTTP_BRIDGE_REPORT.md`, `PHASE2_*.md`, `EXTENSION_PRESSURE_REGISTRY.md`,
  `reuse_audit/`).

## Rules

1. Production changes MUST be implemented under `../research_agent_v24/`
   (code in `src/`, tests in `tests/`, decisions in `docs/decisions/`).
2. When a prototype capability is adopted in production, the canonical
   version lives under `../research_agent_v24/`; this directory keeps the
   original artifact as evidence and is not updated further.
3. Do not add new prototype tracks here without a decision record.
4. Fixtures here are read-only inputs for offline tests; do not edit them
   to make a test pass — fix the code or supersede the fixture explicitly.

## Canonical pointers

- Production app: `../research_agent_v24/README.md`
- Current state: `../research_agent_v24/docs/CODEX_HANDOVER_CURRENT.md`
- Repository ownership/tree: `../research_agent_v24/docs/REPOSITORY_LAYOUT.md`
