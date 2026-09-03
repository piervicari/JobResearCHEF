# 0016 — Task-difficulty LLM routing with quality-aware fallback

Status: **ACCEPTED + IMPLEMENTED FOR P0 JOB ANALYSIS**  
Date: 2026-09-02

## Context

The user already validated a fallback-routing pattern in a separate News Assistant project and wants the Research Agent to reuse **only that routing behavior**, not any news-specific ranking, dedupe, retrieval, or evidence logic.

The Research Agent also has heterogeneous LLM work: mechanical JSON repair is not the same problem as normal job interpretation, and ambiguous semantic adjudication is harder again. Using the strongest model for every request is wasteful; using one weak/free model for every request risks semantic misses.

## Decision

Use deterministic **task lanes**, each labelled by difficulty. Do not spend an LLM call deciding how difficult another LLM call is.

```text
EASY
  json_repair
  optional future job_light_classification

MEDIUM
  job_analysis              <- current P0 default

HARD
  ambiguous_job_review      <- used only when normal analysis remains ambiguous
  internship_program_research (future)
```

Each lane has an explicit ordered model chain. The routing policy is copied from the user's News Assistant:

1. call the primary model;
2. for Google only, retry the **same model first** when the failure is plausibly transient and the route explicitly allows it;
3. do not waste a same-model retry on HTTP 429 without `Retry-After`;
4. if model output is semantically intact but violates JSON/schema, try a cheap micro-repair without resending/reinterpreting the original job context;
5. if recovery fails, try the next explicit fallback target;
6. record provider/model/fallback/retry telemetry;
7. never use a random/free auto-router as the dataset's default model identity.

## P0 route assignments

### MEDIUM — `job_analysis`

```text
Google Gemini 3.7 Flash / medium
  -> Google Gemini 3.6 Flash / high
  -> OpenRouter MiniMax-M3:free / medium
```

### HARD — `ambiguous_job_review`

```text
Google Gemini 3.7 Flash / high
  -> Google Gemini 3.6 Flash / high
  -> OpenRouter MiniMax-M3:free / medium
```

### EASY — repair

```text
Google Gemini 3.5 Flash-Lite / minimal
```

If repair fails, the parent request continues through its normal fallback chain.

## Benchmark rationale

Model selection is informed by Artificial Analysis data retrieved on 2026-09-02, but the Artificial Analysis Intelligence Index is **not a benchmark of our exact job-classification task**. Therefore these assignments are a rational starting point, not a substitute for a real-job golden-set benchmark.

Current Artificial Analysis values used:

- Gemini 3.7 Flash: Intelligence Index 51 low / 53 medium / 56 high; very high output speed; 1M context.
- Gemini 3.6 Flash high: Intelligence Index 52.
- MiniMax-M3: Intelligence Index 45; inexpensive and fast enough to be a useful cross-provider fallback; 1M context.
- Gemini 3.5 Flash-Lite: Intelligence Index 37 and very high throughput, appropriate for mechanical/low-risk work rather than ambiguous semantic adjudication.

Source snapshot and URLs are recorded in `docs/LLM_ROUTING_BENCHMARK_2026-09-02.md`.

## Why task lanes instead of per-job dynamic routing

A separate model-based difficulty classifier would:

- add a call for every batch/job;
- introduce another failure mode;
- make routing harder to reproduce;
- often cost more than the intelligence saved.

The normal full job analysis is therefore always `MEDIUM`. Only explicit unresolved/ambiguous cases are later promoted to `HARD`.

## Implementation implications

- Default `analyze-pending` route is `job_analysis`.
- `--route` can choose another configured task lane.
- `--model` remains only as an emergency/testing override and deliberately disables fallback for that run.
- Google and OpenRouter keys are read from `.env` / environment, never committed.
- Successful analysis stores the actual semantic model used. If a JSON repair was required, the repair model is appended to provenance instead of replacing the semantic-origin model.

## Trade-offs

### Accepted

- Some same-provider fallbacks may share quota/capacity failure modes. Cross-provider MiniMax remains the final resilience layer.
- MiniMax-M3 is weaker than the primary hard-route model on the current Artificial Analysis index; fallback prioritizes availability over identical quality.

### Rejected for now

- automatic OpenRouter free-model router;
- per-job model selection by another LLM;
- strongest/high-reasoning model for every normal job;
- deterministic semantic classification as a fallback.

## Supersedes

This decision supersedes the model-selection/no-retry parts of decision `0015`. The structured batch contract, strict job-ID validation, local queue, and source/AI separation from `0015` remain valid.
