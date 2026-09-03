# 0040 — Targeted semantic cleanup instead of blanket prompt-version reanalysis

- **Date:** 2026-09-02
- **Status:** Accepted + implemented

## Decision

When the semantic contract changes in a way that only affects a narrow persisted state, do not automatically re-analyze every historical AI row solely because `prompt_version` changed.

For the `cyber-job-v3` change introduced by decision 0035, requeue only active `SourceJob` rows that are still `NEEDS_MORE_DETAIL` **and already have at least 1,000 characters of effective description**. These rows contradict the current contract because enough evidence is present to require a binary `CYBER` / `NON_CYBER` decision.

The cleanup is exposed as `research-agent requeue-semantic-cleanup` and performs zero network and zero LLM requests by itself.

## Rationale

The P0 AI-resume report showed two Detectify jobs with 4.5k–5.8k character descriptions still persisted as `NEEDS_MORE_DETAIL`. They were analyzed before the v3 semantic guardrail existed. Re-analyzing every older job just because the prompt version changed would consume free-provider quota even when the changed rule cannot affect those rows.

Targeted migration preserves correctness without turning prompt-versioning into an expensive global replay mechanism.

## Implementation implications

- select only `ai_status=NEEDS_MORE_DETAIL`, active jobs;
- compute the same effective detail-preferred input used by JobAnalyzer;
- require effective description length >= configured cleanup threshold (current operational default 1,000 chars);
- mark selected rows `PENDING_AI` and clear stale AI errors;
- retain all prior `JobAiAnalysis` rows for audit/history;
- subsequent `analyze-pending` creates the new current analysis under the current prompt/input version.

## Trade-offs / rejected alternatives

- **Blanket reanalysis on every prompt bump:** rejected for P0 because it wastes scarce free API capacity and most historical decisions are unaffected.
- **Mutating old AI results in place:** rejected because it destroys auditability and provenance.
- **Deterministically turning these rows into NON_CYBER:** rejected; code only identifies a contract inconsistency, the LLM still owns the semantic classification.

## Future note

If a future prompt/taxonomy change materially affects all roles, introduce an explicit broader replay/migration command rather than silently overloading this targeted cleanup.
