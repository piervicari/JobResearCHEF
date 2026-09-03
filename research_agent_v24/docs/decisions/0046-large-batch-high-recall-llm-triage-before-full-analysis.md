# 0046 — Large-batch high-recall LLM triage before full analysis

**Status:** Accepted / implemented in V23  
**Date:** 2026-09-02

## Decision

Insert a cheap semantic triage stage before the full JobAnalyzer for large raw catalogs.

Initial operating point:

- 100 jobs per triage LLM request;
- MiniMax M3 `:free` primary, Retry-After-aware one retry;
- MiniMax M2.7 `:free` fallback;
- Gemini 3.5 Flash-Lite final fallback;
- compact input: company, title, location, source metadata, ~1.6k description snippet;
- compact output: `job_id`, `candidate_cyber`, optional short reason.

The triage is deliberately high-recall. It can mark a job NON_CYBER only when it is clearly non-cyber. Cyber or ambiguous jobs remain `PENDING_AI` and proceed to the full JobAnalyzer.

## Why

With free providers the binding resource is currently calls/rate limits rather than token billing. Sending every Stripe job directly through the rich 10-job JobAnalyzer would require dozens of calls. A 100-job compact triage can reduce a ~500-job catalog to ~5–6 first-pass calls and reserve full extraction calls for plausible cyber roles.

## Implications

- raw jobs are still stored before triage;
- no deterministic keyword semantic filter is reintroduced;
- triage decisions are versioned in `JobAiAnalysis` with `triage:` model prefix and their own prompt/schema versions;
- clear NON_CYBER rows leave the full queue;
- candidates stay durable `PENDING_AI` if the triage call fails or classifies them as possible cyber;
- triage/full analysis can be scoped to a portal ID for one-employer probes.

## Trade-offs

A larger batch increases risk of skipped/mixed IDs. Strict set equality validation rejects malformed batches and routes through repair/fallback; no missing ID is silently accepted. The 100-job value is an initial tested configuration, not a permanent optimum.
