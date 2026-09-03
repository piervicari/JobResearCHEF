# 0038 — MiniMax-first, Retry-After-aware free routing

**Status:** Accepted + implemented

**Date:** 2026-09-02

## Decision

For active semantic routes, use the following free-only order:

1. `openrouter/minimax/minimax-m3:free`;
2. `openrouter/minimax/minimax-m2.7:free`;
3. `google/gemini-3.6-flash`.

MiniMax M3 may retry the same target exactly once **only** when OpenRouter returns a transient error with an explicit `Retry-After`. The wait is bounded to 90 seconds. OpenRouter transient failures without `Retry-After` fall through immediately.

## Why

Empirical P0 runs repeatedly showed Gemini 3.6 Flash consuming long waits (up to the 300-second timeout, or ~206 seconds before a 503) while MiniMax M3 completed equivalent batches in single-digit seconds when available. The latest AI-resume run also showed the complementary failure mode: MiniMax M3 returned a shared-upstream-pool 429 with `Retry-After: 60`. The previous router ignored that actionable retry signal because OpenRouter same-target retries were disabled.

The goal is therefore not “MiniMax is always better”; it is to optimize the observed operational path while remaining resilient to free-tier scarcity.

## Implementation

- OpenRouter routes can now use `transient_retries`.
- OpenRouter same-target retries are permitted only when the provider supplies `Retry-After`.
- M3: `transient_retries=1`, `max_retry_wait_seconds=90`.
- M2.7 is an additional free cross-model fallback.
- Gemini 3.6 Flash remains the final cross-provider fallback.
- `openrouter_free_only=true` remains enforced.

## Trade-offs

- A temporary M3 429 can add up to ~90 seconds before fallback. This is intentional because the user prefers waiting over paid API use.
- M2.7 is weaker/older than M3; it is present for resilience, not preferred quality.
- OpenRouter free endpoints remain shared/rate-limited and cannot provide hard availability guarantees.
- Gemini remains available as a final provider-diversity fallback even though recent latency has been poor.

## Evidence

- `docs/reports/p0_ai_resume_20260902-161701.log`
- prior P0 pilot/detail-follow-up reports under `docs/reports/`
