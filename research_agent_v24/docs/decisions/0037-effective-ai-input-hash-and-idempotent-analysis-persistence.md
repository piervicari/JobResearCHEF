# 0037 — Effective AI input hash and idempotent analysis persistence

**Status:** Accepted + implemented

## Decision

`JobAiAnalysis.input_payload_sha256` must represent the **effective payload actually supplied to the LLM**, including second-stage detail enrichment. It must never fall back to the listing/source payload hash when the effective AI input differs.

Persistence of an analysis version is idempotent for the key:

`(source_job_row_id, model, prompt_version, schema_version, effective_input_payload_sha256)`.

If that exact key already exists, update/reuse the row rather than inserting a duplicate and crashing on the unique constraint.

The semantic prompt version is bumped from `cyber-job-v2` to `cyber-job-v3` because the P0 contract changed materially in decision 0035: substantive descriptions must receive a binary CYBER/NON_CYBER decision.

## Why

The V18 Wazuh follow-up exposed a persistence bug after detail enrichment:

1. Wazuh detail pages were fetched successfully and the effective LLM input changed.
2. `_analysis_input()` correctly computed a new hash from the enriched title/location/description.
3. `analyze_pending_jobs()` incorrectly persisted `SourceJob.payload_sha256`, the original listing hash.
4. The same model/prompt/schema therefore collided with an older analysis row and SQLite raised `UNIQUE constraint failed`.

This was a bookkeeping bug, not an LLM or network failure.

## Implementation implications

- use `AnalysisInput.payload_sha256` when creating `JobAiAnalysis`;
- exact duplicate version keys are idempotent and update/reuse the existing analysis row;
- keep historical rows when effective input, model, prompt version, or schema version changes;
- bump `llm.prompt_version` to `cyber-job-v3`;
- add regression tests for detail re-analysis and exact same-input replay;
- use `scripts/run_p0_ai_resume.sh` after this incident so already-fetched Wazuh details are re-analyzed without additional career-site traffic.

## Trade-off

Updating an exact same version row means repeated stochastic calls with the exact same version key do not create an unbounded history. Historical provenance remains preserved across meaningful version dimensions (input/model/prompt/schema). If repeated stochastic samples become analytically valuable later, add an explicit `analysis_run_id` rather than weakening the version key accidentally.
