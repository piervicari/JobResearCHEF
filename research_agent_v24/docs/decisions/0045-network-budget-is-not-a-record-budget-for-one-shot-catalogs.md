# 0045 — Network budget is not a record budget for one-shot catalogs

**Status:** Accepted / implemented in V23  
**Date:** 2026-09-02

## Decision

For adapters that retrieve an entire structured catalog in one HTTP response, do not discard already-received jobs merely because the low-impact HTML pilot uses a small `max_jobs_per_portal` cap.

V23 introduces `bulk_catalog_max_jobs_per_portal` and marks one-shot Greenhouse and Ashby adapters as `bulk_catalog=True`.

Pilot safety remains bounded by:

- concurrency;
- requests per host/run;
- pages per portal;
- retries;
- inter-request timing.

The V23 pilot allows up to 2,000 records from a one-shot bulk catalog while retaining the existing three-request/one-page/zero-retry network envelope.

## Why

A Greenhouse response containing hundreds of jobs costs one HTTP request. Truncating 500 jobs to 10 does not protect the user's IP; it only destroys coverage. Network safety and record ingestion are separate dimensions.

## Implications

- Greenhouse can persist the full current Stripe catalog from one API response;
- the same principle can later be extended to other proven one-shot structured sources;
- paginated APIs such as Workday/Lever remain governed by page/request budgets and are not automatically treated as unlimited catalogs.

## Trade-offs

Large catalogs increase local DB writes and downstream semantic workload. That is handled separately by decision 0046 (large-batch semantic triage), rather than by throwing away source records.
