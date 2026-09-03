# 0027 — Accept P0 end-to-end pilot, but gate scale-out on detail quality

**Status:** ACCEPTED  
**Date:** 2026-09-02

## Decision
The first end-to-end P0 pilot is accepted as evidence that the V2 architecture works across network discovery, durable SourceJob persistence, routed LLM analysis, fallback, and AI result storage. It is **not** evidence that parser/detail quality is yet sufficient for broad rollout.

## Evidence
Pilot cohort: Detectify, Trellix, Horizon3.ai, Safe Security, Wazuh.

- 5 portals, 8 total HTTP requests.
- Every request returned HTTP 200; zero retries, zero 403/429/challenge signals.
- 36 jobs persisted as PENDING_AI.
- 4 LLM batches analyzed all 36 jobs.
- Gemini 3.6 Flash completed 3 batches; one 503 immediately fell back to MiniMax M3 :free, which completed successfully.
- Result: 4 CYBER, 24 NON_CYBER, 8 NEEDS_MORE_DETAIL.

## Why scale-out is not yet approved
The pilot exposed a source-quality problem hidden by the successful pipeline:

1. Generic official-HTML discoveries often contain only title + URL and no description/location.
2. At least two CYBER rows were classified from title alone, so their skills/experience extraction is necessarily empty.
3. Trellix produced a bogus `Find Jobs` vacancy from a navigation link.
4. `NEEDS_MORE_DETAIL` is therefore often a data-acquisition issue, not an LLM issue.

## Implementation consequence
Before broadening beyond a small cohort:

- remove obvious navigation-link false positives from generic discovery;
- correct known structured ATS mappings rather than teaching the generic parser each branded portal;
- add a second-stage, bounded detail-page enrichment queue;
- re-run AI only when detail content changes;
- keep the original listing observation immutable/auditable and store detail provenance separately.

## Trade-off
This adds a small number of targeted requests after the first AI pass. That is preferable to fetching every job detail page upfront: we preserve the low-impact network profile while obtaining full descriptions only for jobs likely to matter.
