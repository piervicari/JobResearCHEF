# 0029 — Correct Trellix to Workday; generic navigation links are not vacancies

**Status:** ACCEPTED  
**Date:** 2026-09-02

## Decision
Trellix is no longer treated as a generic/custom HTML jobs source. Its official current job listing sends applications to the Trellix `EnterpriseCareers` Workday tenant, so the registry source is corrected to:

`https://trellix.wd1.myworkdayjobs.com/EnterpriseCareers`

with ATS family `Workday`.

The generic HTML adapter also rejects additional navigation labels such as `Find Jobs`, `Find a job`, and `Job openings` as vacancy titles.

## Why
The P0 pilot saved a single Trellix pseudo-job titled `Find Jobs`. Improving the generic parser around this particular portal would be the wrong abstraction: a structured official source already exists.

## Evidence and audit
Registry correction artifact:

`data/portal_resolution/registry_corrections_run27_v1.csv`

The correction is represented as an audited registry UPDATE, and the synchronized master is exported as:

`data/company_universe/master_company_universe_v1_11_registry_corrections_run27.csv`

## General rule
When an official branded careers page exposes a stable structured ATS endpoint, prefer resolving the registry to that endpoint. Generic HTML remains a fallback, not the preferred source.
