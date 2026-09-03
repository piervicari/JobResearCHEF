# 0022 — Five-minute timeouts for free LLM attempts

**Status:** ACCEPTED + IMPLEMENTED  
**Date:** 2026-09-02

## Context

The first live JobAnalyzer batch showed that free Gemini capacity can return temporary 503s or remain slow under load. The user prefers waiting longer rather than prematurely abandoning a free request. Live heartbeat output now makes a long wait observable instead of silent.

## Decision

1. Allow up to **300 seconds (5 minutes) per LLM attempt** for all active Research Agent LLM routes, including schema repair.
2. Keep `progress_heartbeat_seconds: 15`, so a pending request remains visibly alive.
3. Normal `job_analysis` keeps **zero same-model retries**. A timed-out/failed attempt falls through to the next free model instead of potentially waiting another five minutes on the same model.
4. The active free-only MEDIUM chain remains:
   - Gemini 3.7 Flash medium — 300s;
   - Gemini 3.6 Flash high — 300s;
   - MiniMax-M3 `:free` via OpenRouter — 300s.
5. HARD tasks may retain the previously approved same-model transient retry on the primary model. This means a HARD route can intentionally take materially longer than a normal job-analysis batch.
6. Jobs remain durable in `PENDING_AI` if every free route fails; no paid endpoint is introduced to reduce latency.

## Why this is deliberately not an infinite wait

Free capacity can be slow, but a hung connection still needs a bound. Five minutes is long enough to tolerate substantial provider-side queuing while preserving eventual fallback and an auditable worst-case duration.

## Worst-case latency

For ordinary `job_analysis`, the configured upper bound from request timeouts alone is roughly:

```text
Gemini 3.7 Flash   5 min
+ Gemini 3.6 Flash 5 min
+ MiniMax-M3       5 min
-------------------------
~15 min maximum request wait
```

Provider failures that return immediately shorten this considerably. Heartbeats are emitted throughout pending requests. HARD routes can be longer because they may retry their primary model once.

## Trade-offs

- **Pro:** fewer unnecessary fallbacks caused solely by free-provider slowness.
- **Pro:** preserves the free-only cost constraint.
- **Pro:** heartbeat output removes the previous long silent wait.
- **Con:** tail latency is intentionally higher.
- **Con:** a full three-model failure can take about fifteen minutes for MEDIUM analysis. This is acceptable because analysis is asynchronous with respect to career-site discovery and jobs remain queued.
