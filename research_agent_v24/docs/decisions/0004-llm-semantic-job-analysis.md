# Decision 0004: LLM owns semantic job interpretation; deterministic code owns mechanics

- Status: Accepted
- Date: 2026-09-02

## Decision

Deterministic title/description/seniority keyword rules must no longer decide whether a vacancy is cyber,
what role it represents, or what seniority it has. Those are semantic questions with high market
ambiguity and are delegated to an LLM.

Deterministic code remains responsible for network access, ATS adapters, batching, schema validation,
retry/backoff, persistence, deduplication, job identity, lifecycle and scheduling.

Principle:

> LLM interprets meaning. Code executes and validates.

## Why

The market uses inconsistent names. The same title can mean different things across companies and cyber
roles often lack explicit cyber keywords. Conversely, generic "security" titles may not be cybersecurity.
Deterministic rules create avoidable false positives and false negatives.

## Implementation shape

A `JobAnalyzer` orchestration component takes source job data in batches and requires structured output.
It is not an autonomous agent and does not get unrestricted DB/network access.

Example output for one job:

```json
{
  "job_id": "source-id",
  "domains": ["cybersecurity"],
  "role_family": "Security Engineering",
  "specializations": ["Application Security"],
  "seniority": "senior",
  "years_experience_min": 5,
  "years_experience_max": null,
  "skills_required": ["Python", "threat modeling"],
  "skills_preferred": ["SAST", "DAST"],
  "degree_requirement": null,
  "certifications": []
}
```

Unknown values should be `null`/empty, not guessed.

## Batch strategy

Batching is desirable to reduce unnecessary LLM calls, but batch size is **not hardcoded yet**. It must
be benchmarked for:

- classification accuracy;
- JSON/schema failures;
- jobs skipped inside a batch;
- cross-job contamination;
- latency and token cost.

Start by testing small/medium batches (for example 10 vs 20) against a manually labeled real-job set.
A single batch call may both classify cyber relevance and extract the initial AI analysis; two-stage LLM
calls should only be introduced if measured quality/cost justifies them.

## Critical guardrail

A listing with an ambiguous title must not be rejected merely because the listing page lacks description.
If classification confidence is insufficient, fetch the detail page and classify with fuller context.

## Current implementation impact

This target behavior supersedes the product intent of
`docs/architecture/0005-deterministic-filtering-and-reclassification.md`.
The current runtime still implements that ADR and therefore requires a migration before this decision is
fully live.
