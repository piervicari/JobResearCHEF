# Dashboard analytics validation v2

Date: 2026-09-01
Result: **PASS**

## Requirement closure

The dashboard now exposes every minimum analytics family named in the handover:

- active, latest-run, today, rolling-seven-day and closed job counts;
- official-only, LinkedIn-only and cross-source counts;
- active-job breakdowns for country, company, cyber category, seniority (including internship versus
  junior), workplace type and source;
- filters for keyword, country, company, category, seniority, workplace, source, filter state,
  lifecycle and discovery age;
- company records, clusters, resolved/unresolved clusters, unique/ever-scanned/scannable/suspended
  portals and health/stale counts;
- coverage by discovery geography, sector and adapter;
- last-run duration, request and HTTP 2xx/3xx/4xx/5xx/429 counts, retries, failed domains, parser
  failures, unexpected complete-empty snapshots, discovered/new/updated/closed and duplicate counts.

## Current rendered state

The local current database rendered 48 active jobs, 60 closed jobs, 589 resolved of 11,798 clusters,
524 active portals, 214 ever scanned, 492 scannable and 32 suspended. The latest run was run 29:
32.835 seconds, 27 requests, 27 HTTP 2xx, zero 429, failed domains, parser failures and empty
anomalies.

The source lifecycle table contains 5,789 active observations: 2,344 complete and 3,445 incomplete.
The review queue contains 48 jobs: 22 with at least one complete source and 26 incomplete-only.

## Verification

- The 169-test offline suite includes deterministic activity, six-dimension breakdown, source
  overlap, geography/sector totals, HTTP diagnostic, failed-domain, parser-failure, expected/unknown
  empty and stale-route assertions.
- Query execution against the working database returned all six dimensions, 507 sector rows whose
  record counts sum exactly to 12,503, and exact current coverage metrics.
- Streamlit 1.62 rendered all five tabs in the in-app browser. DOM inspection verified the new
  metrics and controls in Jobs & sources, Coverage and Runs.
- Visual inspection confirmed usable layouts for job analytics and run diagnostics; the browser
  console contained zero errors.
