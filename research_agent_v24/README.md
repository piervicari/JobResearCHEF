# RESEARCH AGENT - PIER

Local-first research agent that monitors a curated set of employers through
their official career sites, persists raw discoveries durably, and uses a
free-only LLM (with retry-aware routing) to interpret job semantics in
cybersecurity. Current product line: `V2.6` (post-cleanup).

## Setup

Requirements: Python 3.12+ and `uv`.

```bash
uv sync --dev --extra dashboard
uv run research-agent bootstrap-secrets
./scripts/bootstrap_runtime_db.sh
./scripts/ensure_dashboard.sh
```

The persistent runtime DB lives at
`~/.local/share/research-agent/research_agent.db`. The dashboard binds to
`http://127.0.0.1:8501`. The project-local `data/research_agent.db` is the
legacy V1 path and is no longer touched by the operator flow.

## One-command operator flow

```bash
./scripts/run_core_trial.sh
```

The script syncs development + dashboard dependencies, reuses persistent
secrets, initializes/migrates the persistent runtime DB, ensures the
Streamlit dashboard is running, and runs a bounded core-employer scan.
A healthy managed dashboard is not started twice.

## Current V2 product path

```text
data/target_employers/tier_s_operational_sources_v1.csv
  → scripts/prepare_tier_s_operational_sources.sh
  → research-agent scan-discover --portal-id <id>
  → research-agent triage-pending --portal-id <id>
  → research-agent analyze-pending --portal-id <id>
  → research-agent show-ai-results
  → dashboard at http://127.0.0.1:8501
```

Auxiliary commands used in the same path:

- `research-agent adapter-coverage` — zero-network adapter selection check.
- `research-agent prepare-v2-source-jobs --dry-run` — backfill legacy source
  jobs into the V2 schema before any live LLM call.
- `research-agent enrich-details` — selective, same-host detail enrichment
  for CYBER / NEEDS_MORE_DETAIL jobs whose listing response lacks
  description.
- `research-agent ingest-linkedin-csv path/to/linkedin_jobs.csv` — manual
  LinkedIn import (no scraping, no automation).
- `research-agent llm-preflight` — verify LLM credentials without external
  traffic.

## Controlled probe of a `READY_TO_PROBE` portal

`READY_TO_PROBE` rows land in the registry as `scan_enabled=False` so the
default scanner skips them. To probe a single one explicitly, use
`--include-disabled` together with an explicit `--portal-id`:

```bash
uv run research-agent scan-discover \
  --database-url sqlite:///$HOME/.local/share/research-agent/research_agent.db \
  --portal-id <id> --include-disabled
```

`--include-disabled` is rejected unless at least one `--portal-id` is
given, and cannot be combined with `--limit`. It does not modify the
database; the next normal `scan-discover` will still honour
`scan_enabled`.

For controlled probes the scanner budget is overridden on the
command line via `RESEARCH_AGENT_SCANNER__GLOBAL_CONCURRENCY=1` and
`RESEARCH_AGENT_SCANNER__MAX_RETRIES=0` so a single portal is hit
sequentially and conservatively. The persisted YAML default of
`global_concurrency=8` only applies to bulk / full-registry runs.

## Google structured-RPC probe

`scripts/run_google_careers_probe.sh` is the next Tier-S validation
operator action. It uses the persistent runtime DB, ensures the managed
dashboard, scans the Google catalog sequentially with a Google-only
request envelope, runs 100-job high-recall triage batches plus
candidate-only rich analysis, and writes
`output/test_runs/google_careers_probe_*.log`. Upload the log and
compare it against current web-visible Google security vacancies before
declaring Google PASS/FIX.

## Network safety

The persisted `config/settings.yaml` defaults are
`global_concurrency=8`, `per_domain_concurrency=1`,
`per_domain_min_interval_seconds=1.0`, `max_retries=2`,
`max_response_bytes=20MB`, no rotating proxies, no fingerprint
spoofing, no CAPTCHA bypass, no browser automation. Respect
`Retry-After`. `max_response_bytes` defaults to 20 MB so a normal
structured Ashby / Greenhouse / Workday catalog lands in a single
response.

## AI budget

LLM routing is free-only. Full analysis chain:
`minimax/minimax-m3:free → minimax/minimax-m2.7:free → google/gemini-3.6-flash`.
Triage chain: `m3:free → m2.7:free → google/gemini-3.5-flash-lite`.
M3 may retry once only when OpenRouter supplies `Retry-After`. No paid
model is introduced.

## Tests

```bash
uv run pytest -q
```

## Documentation map

- `docs/CODEX_HANDOVER_CURRENT.md` — full technical state for the next
  coding agent.
- `docs/ROADMAP_V2.md` — current product roadmap.
- `docs/OPERATIONS.md` — runtime / safety / recovery.
- `docs/TESTING.md` — testing policy and gates.
- `docs/decisions/` — decision log (ADR).
- `docs/reports/` — historical evidence.
- `SECURITY.md` — security policy.
