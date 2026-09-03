# 0044 — Separate canonical careers URL from operational ATS source

**Status:** Accepted / implemented in V23  
**Date:** 2026-09-02

## Decision

Treat the employer-facing careers page and the machine-readable operational job source as different concepts.

For Stripe specifically:

- canonical/careers landing remains `https://stripe.com/careers/search`;
- operational source becomes the verified Greenhouse board `https://job-boards.greenhouse.io/stripe`;
- ATS family becomes `Greenhouse`;
- the existing Greenhouse adapter calls the public Job Board API using board token `stripe`.

The correction is applied through the existing versioned Registry Change mechanism (`registry_corrections_v23_stripe_greenhouse.csv`), not with company-specific scanner code.

## Why

The first core expansion reached Stripe successfully (HTTP 200) but the generic HTML parser returned `EMPTY_INCOMPLETE`. Stripe's official application pages expose Greenhouse-backed applications, while Greenhouse provides a public structured Job Board API. Parsing the vanity careers page is therefore both less reliable and less efficient than using the backend ATS.

## Implications

- `ClusterPortalMapping.resolved_careers_landing_url` remains the human/canonical Stripe careers page;
- the active `Portal` for Stripe is the operational Greenhouse endpoint;
- future runtime DBs can receive the correction idempotently through `apply-runtime-registry-changes`;
- fresh packaged state is synchronized in `master_company_universe_v1_12_stripe_greenhouse.csv`;
- do not add `if company == Stripe` logic to adapters.

## Trade-offs

The operational host shown in scanner telemetry is Greenhouse rather than `stripe.com`. This is desirable because network/rate-limit state should follow the host actually queried. The corporate identity is preserved separately through the cluster mapping and SourceJob company resolution.
