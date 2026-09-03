# 0014 — SourceJob is the durable V2 discovery / Pending-AI queue

Status: **ACCEPTED + IMPLEMENTED**  
Date: 2026-09-02

## Context

The legacy scanner couples successful network discovery to deterministic semantic filtering and canonical-job promotion. V2 must instead preserve discoveries before AI analysis so an LLM outage or prompt/model change never requires re-fetching a career portal.

The existing `SourceJob` table already stores almost all raw source truth, lifecycle timestamps and observation history, including rows that the old deterministic filter excluded. Creating a second parallel raw-job queue would duplicate storage and lifecycle logic.

## Decision

Reuse `SourceJob` as the durable discovery layer.

V2 flow:

```text
official portal / ATS
        ↓
network scan
        ↓
SourceJob
        ↓
PENDING_AI
        ↓
JobAnalyzer (later P0 step)
        ↓
CYBER / NON_CYBER / NEEDS_MORE_DETAIL
```

A V2 discovery scan MUST NOT run `VacancyFilter` or make semantic title/description/seniority/geography decisions.

### SourceJob additions

Store:

- native source job ID separately from any application-owned collision-safe storage identity;
- resolved company cluster/name when available, while preserving raw source company text;
- `ai_status`;
- AI attempt/error/analyzed timestamp metadata.

New or content-changed rows become `PENDING_AI`. An unchanged row that has already been analyzed does not need to be requeued merely because it was seen again.

### AI analysis storage

AI interpretation is versioned separately in `JobAiAnalysis` with:

- source job row ID;
- model;
- prompt version;
- schema version;
- analysis timestamp;
- cybersecurity / needs-more-detail result;
- complete structured JSON;
- validation/error state.

Raw source fields are never overwritten by AI output.

## Why

- scanner reliability is independent from LLM availability;
- no duplicate raw queue/database layer;
- previously downloaded descriptions are reusable;
- model/prompt changes can reprocess local data without network traffic;
- lifecycle/history already exists on SourceJob;
- lower implementation complexity.

## Trade-off

`SourceJob` temporarily contains non-cyber discoveries until AI classification. This is intentional technical queue state, not the final cyber product dataset.
