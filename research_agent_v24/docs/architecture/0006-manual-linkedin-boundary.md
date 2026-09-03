# ADR 0006: LinkedIn as a manual, provenance-rich input

- Status: Accepted
- Date: 2026-08-30

## Context

LinkedIn is in scope as a source, but automated crawling, login automation and anti-bot bypass are
outside the MVP's compliance and reliability boundaries.

## Decision

- LinkedIn jobs enter through a strict user-supplied CSV template.
- Each file is recorded as an import batch with path, checksum and row count; identical files are
  idempotent.
- Imported jobs use the same filter, cluster resolver, deduplication, observation and canonical-job
  pipeline as official sources.
- Company resolution is exact and conservative. Ambiguous or unknown names remain unresolved rather
  than receiving an invented Corporate Cluster ID.
- Manual imports are incomplete snapshots and cannot close previously observed jobs.

## Consequences

LinkedIn contributes to source overlap and vacancy discovery without becoming a fragile required
dependency. Coverage remains dependent on deliberate user exports until an approved official input
path exists.
