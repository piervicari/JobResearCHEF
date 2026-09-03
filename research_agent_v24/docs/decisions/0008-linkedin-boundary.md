# Decision 0008: LinkedIn automation is outside the critical path

- Status: Accepted
- Date: 2026-09-02

## Decision

Do not depend on automated LinkedIn scraping for the core product. Official company career sites / ATS
sources are the primary operational source.

Retain the already implemented manual LinkedIn CSV/import path as an optional discovery/input mechanism.

## Why

- Official career systems are closer to the employer source of truth.
- They are generally better for stable job IDs, job detail retrieval and lifecycle tracking.
- LinkedIn is hostile to the kind of automation required here and would introduce account/session/CAPTCHA
  risk into the critical path.
- The existing manual import costs little to keep and may still be useful opportunistically.
