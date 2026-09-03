# 0017 — Preflight safety and optional operator contact

**Status:** Accepted + implemented

## Decision

1. `operator_contact` is optional metadata in the scanner User-Agent. It must never block a dry-run and is not required for the low-impact canary.
2. `analyze-pending` must refuse a live LLM call if any selected job has no resolved/raw company identity.
3. AI dry-run reports the count of jobs missing company identity so legacy-data problems are visible before API usage.
4. The distributed V2 baseline database is pre-migrated offline with `prepare-v2-source-jobs`; the command remains available for older/local databases and reproducibility.

## Rationale

The first local dry-run exposed two avoidable usability/safety problems: legacy rows still had blank company names and `scan-canary --dry-run` demanded an operator contact even though it performs zero network traffic. Both checks were in the wrong place.

A dry-run should have no external prerequisites. A live LLM call, on the other hand, should fail closed if identity context is incomplete because company identity materially affects job interpretation and auditability.

## Implementation implications

- Scanner uses the stable `research-agent-pier/0.2` User-Agent when no contact is configured.
- Optional contact, when provided, is appended to the User-Agent.
- `analyze-pending --dry-run` prints `missing_company`.
- Live `analyze-pending` exits before constructing/sending an LLM request when `missing_company > 0`.
- Fresh distributed DB is already converted to the V2 canonical payload envelope and company identity backfill where resolvable.

## Trade-offs

Leaving contact optional gives less operator metadata to a site administrator, but avoids requiring the user to expose an email address and removes an unrelated setup step. Stable low-volume behavior, caching, clear request budgets, and immediate stop on blocking signals remain the primary safety controls.
