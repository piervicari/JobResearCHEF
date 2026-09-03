# 0021 — Free-only LLM routing

**Status:** ACCEPTED + IMPLEMENTED  
**Date:** 2026-09-02

## Context

The user requires the Research Agent to use only models available without per-call payment during the current validation phase. V10 temporarily added GLM-5.3-Flash via OpenRouter as a high-quality fallback, but that endpoint is not guaranteed free. A fallback must never create an unexpected charge merely because free providers are unavailable.

## Decision

1. Remove GLM-5.3-Flash from every route.
2. Normal `job_analysis` uses only:
   - Gemini 3.7 Flash medium;
   - Gemini 3.6 Flash high;
   - `minimax/minimax-m3:free` through OpenRouter.
3. HARD semantic routes use the same free-only model families, with stronger Gemini reasoning where configured.
4. JSON/schema micro-repair remains Gemini 3.5 Flash-Lite.
5. `openrouter_free_only: true` is enabled by default. In this mode, configuration validation rejects every OpenRouter model whose ID does not end in `:free`.
6. Do not silently fall back to a paid endpoint when free quotas/capacity are exhausted. Total failure leaves the job `PENDING_AI` for a later retry.

## MEDIUM route

```text
Gemini 3.7 Flash medium (90s, no retry)
  -> Gemini 3.6 Flash high (120s, no retry)
  -> MiniMax-M3:free via OpenRouter (120s, no retry)
```

## Rationale

Unexpected cost is worse than delayed analysis during the validation phase. The queue is durable, so there is no need to pay merely to avoid temporary provider unavailability. Keeping the chain short also bounds worst-case latency and makes routing behavior easy to audit.

## Trade-offs

- Availability is lower than with paid fallbacks. This is acceptable because jobs remain queued.
- Google API free-tier eligibility and quota are account/provider-side conditions; the application can guarantee that it does not select paid OpenRouter model IDs, but it cannot inspect the billing configuration of the user's Google account.
- If the free-only constraint changes in the future, it must be an explicit new decision rather than a silent config edit.
