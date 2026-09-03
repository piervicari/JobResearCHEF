# 0032 — Use project Python via `uv run python` in operational scripts

- **Date:** 2026-09-02
- **Status:** accepted

## Decision
Operational shell scripts must not invoke a bare `python` executable. Any embedded Python used by project scripts must run through `uv run python` (or another explicitly project-managed interpreter when justified).

## Why
The P0 detail follow-up failed on macOS before doing any network or LLM work because `scripts/bootstrap_latest_pilot_db.sh` invoked `python`, while the user's environment exposes the project interpreter through `uv` and does not provide a `python` command on PATH.

Observed failure:

```text
./scripts/bootstrap_latest_pilot_db.sh: line 5: python: command not found
```

The project already standardizes dependency/environment management on `uv`, so relying on system Python is unnecessary and less portable.

## Implementation
- `scripts/bootstrap_latest_pilot_db.sh`: `python - <<'PY'` -> `uv run python - <<'PY'`.
- Audited the remaining shell scripts for bare `python` invocations. `scripts/final_audit.sh` already uses `uv run python` and needs no change.

## Trade-off
This makes operational scripts depend on `uv`, but `uv` is already a hard operational dependency for the CLI and environment, so this does not add a new requirement.

## Follow-up rule
When adding shell scripts, prefer project-managed executables (`uv run ...`) over assumptions about system-level interpreters.
