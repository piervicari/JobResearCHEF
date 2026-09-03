# 0019 — Separate network health from discovery health; use an isolated AI micro-canary

**Status:** Accepted + implemented in canary CLI / test workflow  
**Date:** 2026-09-02

## Decision

A portal returning HTTP 2xx is not automatically considered extraction-healthy.
The canary reports a separate discovery state:

- `JOBS_FOUND`: at least one job was discovered;
- `EMPTY_COMPLETE`: the adapter claims a complete snapshot but observed zero jobs;
- `EMPTY_INCOMPLETE`: network access succeeded but the adapter/fallback could not prove that zero jobs is the real portal state.

`EMPTY_INCOMPLETE` must not be interpreted as "this employer has no jobs" or "the adapter works".

The first live LLM test is also isolated from the main DB: use the disposable canary DB, analyze only five already-local `PENDING_AI` jobs in a single batch, and inspect structured outputs before any broader AI run.

## Evidence motivating the decision

The 2026-09-02 network canaries produced:

- KPMG / SuccessFactors: 1 request, HTTP 200, 5 jobs;
- PayPal / Workday: 2 requests, HTTP 200, 20 jobs;
- Mercedes-Benz / generic official HTML fallback: 2 requests, HTTP 200, 0 jobs.

Mercedes-Benz had current public job postings, so its zero-job result demonstrated that network success and discovery success are different properties.

Across the three canaries there were 5 total HTTP requests, 0 retries, 0 HTTP 403/429 responses and no access challenge.

## Implementation implications

1. `scan-canary` prints `discovery=...` independently from `status=SUCCESS/FAILED`.
2. `EMPTY_INCOMPLETE` emits an explicit warning.
3. Do not advance broad portal rollout solely because HTTP access is healthy; adapter coverage still needs its own metrics.
4. The first LLM live run must target `data/canary/research_agent_canary.db`.
5. Inspect the resulting AI rows locally before increasing batch size or job count.
6. Load project-local `.env` explicitly into the process environment (without overriding shell/CI variables), because provider clients read API keys with `os.getenv`.
7. Provide a zero-request `llm-preflight` command so missing credentials are caught before a live batch.

## Why not mark every empty result FAILED?

A generic or deliberately incomplete adapter may legitimately be unable to enumerate a portal while still being useful for discovery. Treating every incomplete zero as a transport failure would conflate parser coverage with network reliability and could trigger inappropriate cooldown/retry logic.

## Why stop network canaries here?

Three different hosts/stacks with five total successful requests are enough to proceed to a small AI experiment. They do not prove that every target site will accept future traffic, so rollout must remain gradual, but additional low-value network probes would add traffic without answering a new architectural question.
