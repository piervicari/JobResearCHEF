# 0015 — JobAnalyzer structured batch and provider contract

Status: **ACCEPTED STRUCTURED CONTRACT; ROUTING/MODEL POLICY SUPERSEDED BY 0016**  
Date: 2026-09-02

## Context

V2 delegates semantic interpretation of titles/descriptions to an LLM. We want to minimize unnecessary calls, keep provider/model choice replaceable, and avoid coupling career-site scans to AI availability.

A random model router is useful for smoke tests but is a poor production default for a research dataset because different underlying models can produce different classifications and make regressions difficult to measure.

## Decision

Implement one bounded `JobAnalyzer` over the local `PENDING_AI` queue.

- Provider transport uses an OpenAI-compatible `/chat/completions` contract so OpenRouter or another compatible endpoint can be selected through configuration.
- No API key is stored in repository configuration; the key is read from an environment variable.
- Historical note: this decision originally required an explicit single model. Decision `0016` supersedes that point with explicit task-specific fallback chains.
- Request structured JSON output validated against a strict Pydantic schema.
- The response must contain exactly one unique result for every submitted `job_id`; missing/extra/duplicated IDs invalidate the whole batch.
- No automatic provider retry loop in this layer. Failed batches remain `PENDING_AI`; they can be retried later from local data without re-scanning career sites.
- Batch size and jobs/run are hard-bounded configuration and must be benchmarked rather than maximized blindly.
- Full raw descriptions remain in local storage. Model input may use a bounded head+tail representation only for abnormally long descriptions; this does not modify source truth.
- Every successful analysis records model, prompt version, schema version and input payload hash.

## Initial structured fields

```text
is_cybersecurity
needs_more_detail
role_family
specializations
seniority
years_experience_min / max
skills_required
skills_preferred
degree_requirement
certifications
short_reason
```

All seniorities are valid. The model must prefer null/empty values over unsupported inference.

## State transitions

```text
PENDING_AI
   ├─ clearly cyber ─────────→ CYBER
   ├─ clearly non-cyber ─────→ NON_CYBER
   └─ insufficient detail ───→ NEEDS_MORE_DETAIL
```

A provider/schema failure does not transition the semantic state; it only increments attempt/error metadata.

## Why

- reproducible classification requires knowing which model produced it;
- batches reduce request count;
- strict ID/schema validation catches skipped or mixed jobs;
- local retries avoid new career-site traffic;
- provider/model can be changed without changing database source truth.

## Open question

Benchmark candidate models and batch sizes (initially 5/10/20) on a manually reviewed real-job sample before choosing the default model.
