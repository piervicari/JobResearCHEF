# 0035 — Substantive descriptions require a binary cyber decision

- **Date:** 2026-09-02
- **Status:** ACCEPTED + IMPLEMENTED

## Context

After full Detectify descriptions were fetched, MiniMax returned `NEEDS_MORE_DETAIL` for `Senior Cloud Engineer` and `Staff Engineer Agentic Profile`, even though its own reasons said the core responsibilities were cloud/AI engineering and security was incidental. The output was internally inconsistent: evidence was sufficient, but the status still requested more evidence.

## Decision

`NEEDS_MORE_DETAIL` is reserved for genuinely insufficient evidence.

When the analyzer receives a **substantive description** (current guardrail: at least 1,000 non-whitespace characters), it must return a supported binary classification:

- `CYBER`, or
- `NON_CYBER`.

If security is merely contextual, employer-level, nice-to-have, or incidental to the core responsibilities, classify `NON_CYBER`.

## Why

This preserves the intended division of responsibility:

- code decides whether sufficient source text exists;
- the LLM decides the semantic classification.

It avoids endless detail-fetch loops after the detail is already present and prevents contradictory AI states.

## Implementation

- System prompt explicitly defines the rule.
- Local validation rejects `NEEDS_MORE_DETAIL` / `is_cybersecurity=null` for inputs with >=1,000 characters of description.
- Invalid output enters the existing structured-output repair/fallback path rather than being silently persisted.

## Trade-off

Character count is only a proxy for evidence quality. It is deliberately simple for P0. If real ATS pages later produce long boilerplate with little role information, replace the length guard with a small explicit evidence-quality field rather than adding deterministic job semantics.
