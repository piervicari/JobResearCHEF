# 0023 — Temporarily disable Gemini 3.7 Flash and persist test-run output

**Status:** Accepted + implemented  
**Date:** 2026-09-02

## Decision

Temporarily remove `gemini-3.7-flash` from **all active LLM routes** in the Research Agent.

For normal `job_analysis`, the active free-only route becomes:

1. `google/gemini-3.6-flash` (`thinking=high`, timeout 300s, no same-model retry);
2. `openrouter/minimax/minimax-m3:free` (`thinking=medium`, timeout 300s, no same-model retry).

`gemini-3.7-flash` remains documented as a candidate model but is not called by active routing until explicitly re-enabled after new evidence/benchmarking.

Test-oriented workflows must persist their terminal output under `output/test_runs/` while still streaming it live to the terminal. The project provides wrappers for the AI micro-canary and network canary.

## Evidence / rationale

Two live AI micro-canaries on the same 5-job batch showed poor operational behavior from Gemini 3.7 Flash:

- earlier run: HTTP 503 followed by a read timeout before fallback;
- 2026-09-02 run: one full 300-second read timeout;
- fallback `gemini-3.6-flash` then completed the same batch successfully in about 29.6 seconds.

The objective is a usable personal research system using free APIs. General benchmark quality is not sufficient reason to keep a model first in the route when observed availability/latency is materially worse on the actual workload.

## Implementation

### Active routing

```text
job_analysis / ambiguous_job_review / internship_program_research
    ↓
Gemini 3.6 Flash
    ↓ failure
MiniMax M3 :free
```

Easy JSON repair remains on Gemini 3.5 Flash-Lite.

OpenRouter remains fail-closed with `openrouter_free_only: true`.

### Test output

New helpers:

```bash
./scripts/run_ai_micro_canary.sh
./scripts/run_network_canary.sh <portal_id>
```

They mirror stdout+stderr to timestamped files such as:

```text
output/test_runs/ai_micro_canary_20260902-132900.log
output/test_runs/network_canary_portal_69_20260902-132900.log
```

AI test reports include preflight, DB reset, dry-run, live routing heartbeat/telemetry, and full local AI results. No API-key values are printed.

## Trade-offs

- Removing 3.7 may reduce peak semantic quality on some hard cases.
- In exchange, the current route is much more operationally predictable based on observed evidence.
- MiniMax remains a resilience fallback rather than the preferred model until its quality is tested on the same real-job set.
- Five-minute timeouts remain available because free providers may queue, but no same-model retry is used in these routes.

## Re-enable criterion

Do not re-enable Gemini 3.7 automatically. Reconsider it only after a controlled micro-benchmark shows acceptable success rate and latency on this workload.
