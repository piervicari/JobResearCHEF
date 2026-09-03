# ADR 0003: Strict and idempotent authoritative-master import

- Status: Accepted
- Date: 2026-08-30

## Context

The master v1.5 is authoritative and must not be silently rebuilt or replaced. Its CSV begins with a
UTF-8 BOM, and future jobs will depend on cluster identities.

## Decision

- Parse with `utf-8-sig` and require the exact 32-column schema.
- Reject duplicate or blank primary keys and incomplete resolved rows.
- Record source path, version, SHA-256, timestamps and validation metrics in `ImportBatch`.
- Preserve every source row plus its raw JSON.
- Treat an identical checksum as an idempotent no-op.
- Refuse a different master over an existing import until a deliberate versioned migration workflow
  is used.

## Consequences

Reruns cannot duplicate data, and an accidental replacement cannot detach existing vacancy history.
Wave 6+ will require an explicit synchronizing importer rather than a destructive refresh.

