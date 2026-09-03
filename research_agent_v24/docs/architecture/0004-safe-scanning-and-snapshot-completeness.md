# ADR 0004: Explicit scan bounds and snapshot completeness

- Status: Accepted
- Date: 2026-08-30

## Context

The registry contains 510 operational URLs and some ATS hosts are shared. A default full scan would
be hard to audit and could create unnecessary load. A successful HTTP response is also not proof
that a parser observed the portal's complete vacancy set.

## Decision

- A manual official scan must specify Portal IDs, a stable-order limit, or explicit `--all`.
- Requests use bounded global and per-domain concurrency, a host start interval, conditional cache,
  retry/backoff and `Retry-After`.
- Every portal is an isolation boundary and records its own outcome.
- Structured adapters declare whether their result is a complete snapshot.
- Generic HTML, manual LinkedIn imports, taxonomy reclassification and failed scans are incomplete
  snapshots and can never increment missing counters or close jobs.
- A source job closes only after two successful complete absences; the first anomalous empty
  snapshot degrades portal health without closing anything.

## Consequences

Lifecycle state favors false negatives in closure over destructive false closures. Generic results
may become stale until refreshed by a complete adapter or manually reviewed, but provenance and
history stay intact.
