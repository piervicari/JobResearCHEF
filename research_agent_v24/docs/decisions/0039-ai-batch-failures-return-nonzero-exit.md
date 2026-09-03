# 0039 — AI batch failures return a non-zero process exit

**Status:** Accepted + implemented

**Date:** 2026-09-02

## Decision

`research-agent analyze-pending` must exit non-zero when one or more selected AI batches fail (`api_failures > 0`), while leaving the affected jobs durably in `PENDING_AI`.

## Why

The 2026-09-02 AI-resume run had `batches_succeeded=0`, `api_failures=1`, and `still_pending_jobs=2`, but the CLI process still exited with code 0. This made the surrounding script report `ai_exit_code: 0`, which falsely suggested successful processing.

Queue durability and command success are different concepts:

- preserving jobs for retry is correct;
- telling automation that the run completed successfully is not.

## Implementation

After printing routing telemetry and summary metrics, `analyze-pending` now exits with code 2 when `api_failures > 0`. Operational wrapper scripts already capture the exit code, print local results for debugging, and return the same non-zero code.

## Trade-offs

A partial run can therefore be reported as failed even if some earlier batches succeeded. This is desirable for operational visibility; successful analyses remain persisted and only failed jobs remain pending.
