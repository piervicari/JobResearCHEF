# 0030 — Result views show only the latest AI analysis per SourceJob

**Status:** ACCEPTED  
**Date:** 2026-09-02

## Decision
Human-facing `show-ai-results` views must return the latest AI analysis for each SourceJob rather than every historical analysis record.

## Why
Detail enrichment intentionally causes re-analysis. Historical `JobAiAnalysis` rows are retained for audit/reproducibility, but showing old and new analyses together would make the operational view ambiguous and could double-count jobs.

## Implementation
Use `MAX(JobAiAnalysis.id)` grouped by `source_job_row_id` for the local operational view. History remains queryable in the underlying table.
