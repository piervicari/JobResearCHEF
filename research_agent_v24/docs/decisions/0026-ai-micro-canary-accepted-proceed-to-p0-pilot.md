# 0026 — AI micro-canary accepted; proceed to P0 pilot

Status: ACCEPTED
Date: 2026-09-02

## Evidence

`docs/reports/ai_micro_canary_20260902-134348.log`

Five Apiiro postings were analyzed in one batch. Gemini 3.6 Flash completed in ~31 seconds and
produced 1 CYBER / 4 NON_CYBER results. The outputs correctly treated security-company context as
insufficient by itself: two Customer Success roles and Director of Sales remained non-cyber, while
`AI Research Engineer, Security` was classified as cybersecurity with AppSec/Security Research/AI
Security specializations.

## Decision

The micro-canary is sufficient evidence to proceed with the P0 end-to-end pilot. Do not spend a
P0 cycle benchmarking MiniMax against Gemini merely for model ranking. MiniMax-M3:free remains the
cross-provider fallback.

## Caveat

This does not prove production-level semantic accuracy. A real-job golden set remains a P1 quality
control if pilot errors or ambiguous roles justify it.
