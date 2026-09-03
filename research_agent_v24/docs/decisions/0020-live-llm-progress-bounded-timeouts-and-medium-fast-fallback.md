# 0020 — Live LLM progress, bounded timeouts, and fast MEDIUM fallback

**Status:** PARTIALLY SUPERSEDED BY 0021  
**Date:** 2026-09-02

## Context

The first five-job live AI micro-canary succeeded, but the primary Gemini 3.7 Flash call returned HTTP 503, waited for a same-model retry, and the retry then consumed the previous 600-second read timeout. The user had almost no live feedback while this was happening. Gemini 3.6 Flash eventually succeeded and correctly completed the batch, but the latency/observability behavior is unacceptable for interactive use.

## Decision

1. Every live AI run prints batch start/end plus every provider attempt **before** the request is sent.
2. Attempt output includes provider, model, reasoning level, fallback index, attempt number and the effective timeout.
3. Attempt completion/failure and retry waits are printed immediately, not only in final telemetry.
4. Per-target request timeouts replace the previous effectively unbounded 600-second wait.
5. Normal `job_analysis` is a MEDIUM task and **does not retry Gemini 3.7 Flash on transient failures**. It falls through immediately because the benchmarked intelligence delta versus Gemini 3.6 Flash high is too small to justify long same-model waits.
6. HARD routes may retain one same-model retry, but with a short wait and bounded timeout.
7. Add `z-ai/glm-5.3-flash` via OpenRouter as a strong cross-provider quality fallback before the final free `minimax/minimax-m3:free` resilience fallback.
8. Do not add an arbitrarily long model chain. Extra fallbacks increase tail latency and make failures harder to understand.

## MEDIUM route

```text
Gemini 3.7 Flash medium  (90s timeout, no retry)
  -> Gemini 3.6 Flash high (120s, no retry)
  -> GLM-5.3-Flash via OpenRouter (120s, no retry)
  -> MiniMax-M3:free via OpenRouter (120s, no retry)
```

## HARD route

```text
Gemini 3.7 Flash high (120s, max one transient retry, 20-30s wait)
  -> Gemini 3.6 Flash high
  -> GLM-5.3-Flash via OpenRouter
  -> MiniMax-M3:free
```

## Rationale

The fallback policy should preserve quality when the delta is material, but responsiveness matters. A single transient 503 on a normal batch should not create a ten-minute stall when a nearly equivalent fallback is available. Observability is part of reliability: an operator must always know whether the system is waiting, retrying, falling back, validating, or finished.

## Trade-offs

- Shorter timeouts can abandon a legitimately slow response. The batch remains `PENDING_AI` on total failure, so this is recoverable.
- GLM-5.3-Flash is very inexpensive but not guaranteed free on OpenRouter; if the account cannot use paid models, that attempt may fail and the router continues to the free MiniMax fallback.
- Multiple OpenRouter models still share OpenRouter as a gateway, so they are model fallbacks, not complete provider-gateway independence.


## Supersession note — 2026-09-02

Decision 0021 keeps the observability, bounded timeout, fast MEDIUM fallback, and limited-chain principles from this decision, but removes GLM-5.3-Flash because the project is now explicitly **free-model-only**. No paid OpenRouter model may be attempted.
