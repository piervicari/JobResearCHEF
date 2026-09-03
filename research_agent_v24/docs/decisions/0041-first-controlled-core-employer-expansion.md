# 0041 — First controlled core-employer expansion after P0 validation

- **Date:** 2026-09-02
- **Status:** Accepted + implemented as operator runbook

## Decision

The provider/retry/detail/persistence mechanics are sufficiently validated to stop micro-testing and begin an incremental expansion across the human-curated core employer universe.

The first expansion cohort contains 10 employers and reuses the already-tested `scan-pilot` safety envelope in two sequential groups of five:

1. Proofpoint, Snyk, Arctic Wolf, Abnormal Security, Claroty;
2. Stripe, Visa, Airbus, Datadog, GitLab.

This cohort is recorded in `data/pilot/p0_core_expansion_cohort_v0_1.yaml` and executed by `scripts/run_p0_core_expansion.sh`.

## Why these employers

- all are already in the curated core target set;
- all currently have scannable/healthy portal records in the packaged registry snapshot;
- first group is security-heavy and should provide useful cyber yield;
- second group adds payments, aerospace and cloud/dev-platform diversity;
- deliberately avoids immediately exercising the highest-risk must-not-miss portals such as Google, Microsoft, Apple, NVIDIA and similar names;
- avoids using a known Taleo gap as the dominant signal in this first scale-out step.

## Network posture

The expansion does **not** relax canary safety mechanics:

- concurrency 1;
- zero retries at career sites;
- <=3 requests per portal per scan invocation;
- <=1 page per portal;
- <=10 jobs per portal;
- 10 second inter-portal spacing;
- stop on 401/403/429/access challenge/robots denial;
- two groups of five preserve the existing tested `scan-pilot` boundary and stop behavior.

Worst-case configured discovery volume is 100 jobs and <=30 career-site HTTP requests across 10 different employers, though actual traffic is expected to be lower.

## Semantic processing

Before expansion, the script applies decision 0040's offline semantic cleanup so stale fully-described `NEEDS_MORE_DETAIL` rows enter the same AI queue as newly discovered jobs. AI runs only after both network groups pass their access gates.

## Trade-offs

- A 10-employer step provides materially more coverage evidence than another 2–5 employer micro-test while remaining bounded.
- We do not jump directly to all 200 core employers because parser/adapter yield and access behavior still need measured expansion data.
- We do not auto-fetch all detail pages during the expansion; selective enrichment remains a second stage so source traffic stays bounded.

## Success criterion

Use the generated `p0_core_expansion_*.log` to assess:

- requests/retries/block signals per portal;
- jobs observed and persisted per employer;
- extraction-empty/incomplete cases;
- LLM batches/provider fallbacks;
- cyber yield and remaining `NEEDS_MORE_DETAIL` rows.

If the cohort is healthy, expand in progressively larger curated batches rather than returning to isolated component micro-tests.
