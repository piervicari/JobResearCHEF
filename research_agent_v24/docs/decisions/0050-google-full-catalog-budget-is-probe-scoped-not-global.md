# 0050 — Google full-catalog network budget is probe-scoped, not global

**Status:** Accepted / implemented in V24  
**Date:** 2026-09-02

## Decision

Do not raise the scanner's global network defaults merely to accommodate Google.

Google Careers currently fixes search pages at 20 records. A full catalog around 3.5k jobs therefore needs roughly 175 RPC requests. `scripts/run_google_careers_probe.sh` supplies a Google-only execution envelope:

- global concurrency: 1;
- per-domain concurrency: 1;
- minimum interval: 1.25 s;
- maximum pages: 200;
- maximum requests/host and run: 220;
- transient HTTP retries: 1;
- structured record cap: 5,000.

The ordinary scanner defaults remain unchanged.

## Why

A 30-request global cap is appropriate for most unknown career portals but cannot prove completeness for Google's fixed-size pagination. Raising the global cap would increase risk for every other employer even though only this verified platform currently needs it.

## Alternatives rejected

- **Globally raise max requests/pages:** unnecessary blast-radius increase.
- **Accept only the first 30 Google pages:** would persist a known partial catalog and fail the employer-level verification goal.
- **Use a broad `security` query to reduce requests:** cheaper but not a complete raw catalog and vulnerable to Google's fuzzy search semantics.

## Trade-offs

The full Google probe is more network-expensive than Stripe's one-shot Greenhouse call. It is still sequential, paced, bounded and isolated to a verified first-party endpoint. Any incomplete scan is marked incomplete, so lifecycle closure must not advance from it.
