# Decision 0006: Reliable identity, sightings and conservative closure

- Status: Accepted
- Date: 2026-09-02

## Decision

Track when each job was first and last observed without storing a duplicate full description on every
scan. A job is not marked closed merely because one scan does not find it.

## Job identity priority

Use the strongest stable source key available:

```text
1. ATS/source external_job_id
2. canonical job URL
3. fallback fingerprint (company + title + location + other stable attributes)
```

Do not equate identical titles with identical jobs.

## Core lifecycle fields

```text
first_seen_at
last_seen_at
seen_count
miss_streak
status            # OPEN | MISSING | CLOSED
content_hash
```

Optional future field:

```text
reopened_count
```

## Closure algorithm

A miss counts only when the portal scan is both successful and known to be a complete/reliable snapshot.

```text
OPEN
  ↓ absent in successful complete snapshot
MISSING (miss_streak = 1)
  ↓ absent in another successful complete snapshot
closure candidate (miss_streak = 2)
  ↓ optional direct GET of the known job URL when feasible
CLOSED only if the evidence still supports absence
```

Failures such as timeout, HTTP 403/429, parser error, challenge page or incomplete generic HTML snapshot
must **not** increment `miss_streak`.

If a missing job reappears, reset `miss_streak` and return it to `OPEN`.

## Content changes

Do not store a duplicate full job record on every sighting.
Compute `content_hash`; only when content changes is versioning potentially required.

Full historical content-version tables are deferred, but storing `content_hash` now preserves the option.

## Why

Two consecutive misses are not sufficient if both scans were unreliable. Closure confidence must be tied
to scan quality, not just count. A direct URL re-check is a simple, high-value final guard when available.
