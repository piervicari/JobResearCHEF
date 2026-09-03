# 0036 — Per-host safety cap for selective detail enrichment

- **Date:** 2026-09-02
- **Status:** ACCEPTED + IMPLEMENTED

## Context

After Detectify was enriched, the remaining eligible detail candidates were concentrated on Wazuh. A global `limit=5` could therefore produce one robots request plus five detail requests against a single host in one follow-up run, which is more aggressive than the canary posture used so far.

## Decision

Keep the global detail limit, but additionally cap **detail pages per host at 2 per run** by default.

With robots lookup this means the usual upper bound for one host in a fresh run is approximately three HTTP requests.

## Why

- Preserve the low-impact network posture validated during canaries.
- Prevent a concentrated backlog on one generic portal from turning a selective enrichment run into a burst against a single domain.
- Progress can remain incremental across repeated manual runs.

## Implementation

- `select_detail_candidates(..., max_jobs_per_host=2)` enforces the cap.
- `enrich-details` exposes `--max-jobs-per-host` (default 2, bounded 1–5).
- Dry-run output prints the effective per-host cap.

## Trade-off

A host with many ambiguous jobs may require several follow-up runs. That is intentional while P0 prioritizes safety and observability over throughput.
