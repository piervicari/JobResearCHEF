# 0043 — Dashboard supervisor and one-command core trial

**Status:** Accepted / implemented in V22  
**Date:** 2026-09-02

## Decision

Add two operational entry points:

- `scripts/ensure_dashboard.sh`: checks Streamlit health on `127.0.0.1:8501`, starts the dashboard only when needed, and binds it to the persistent runtime database.
- `scripts/run_core_trial.sh`: one command that installs/syncs project + dashboard dependencies, checks persistent secrets, bootstraps/migrates the persistent runtime DB, ensures the dashboard is running, then executes the first controlled core expansion.

A healthy dashboard managed by this project and already bound to the requested DB is not relaunched. A managed dashboard pointing to an obsolete version-local DB is restarted once on the persistent runtime DB. An unmanaged process occupying the dashboard port causes a fail-fast message rather than killing an unknown process.

## Why

The dashboard already existed, but its manual command defaulted to the project-local production DB while P0 tests used the pilot DB. That can make a successful scan appear absent in the UI. The user also should not have to remember dependency extras, Streamlit commands, DB environment variables, or whether the dashboard is already running.

## Implications

- normal operator command for the next trial becomes `./scripts/run_core_trial.sh`;
- Streamlit runs in the background under `nohup` and its process/log metadata live under `~/.local/state/research-agent/`;
- dashboard URL is `http://127.0.0.1:8501`;
- on macOS the browser is opened automatically only when the dashboard is newly started;
- the dashboard displays its active database URL and exposes a manual `Refresh data` control.

## Trade-offs

This adds a small process supervisor shell layer instead of adopting Docker/systemd/launchd. That is intentional: the current MVP is local and on-demand, and a platform service manager would be unnecessary complexity at this stage.
