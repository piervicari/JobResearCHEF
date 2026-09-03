# 0025 — First P0 end-to-end pilot cohort

Status: ACCEPTED
Date: 2026-09-02

## Decision

After successful network and AI micro-canaries, move to a five-employer end-to-end pilot instead
of benchmarking models further or scanning core Big Tech employers.

Cohort v0.1:

- Detectify — portal 46
- Trellix — portal 115
- Horizon3.ai — portal 177 (Ashby)
- Safe Security — portal 214 (Lever)
- Wazuh — portal 280

The cohort is not a ranking. It intentionally uses cybersecurity employers that are useful for
semantic yield while being lower-criticality than the must-not-lose core names.

## Network budget

Per portal:

- concurrency 1 globally and per domain;
- <= 3 requests;
- <= 1 listing page;
- <= 10 jobs;
- 0 retry;
- >= 10 s between portals;
- stop the pilot immediately on 401/403/429, access challenge, or robots denial.

## Data isolation

`prepare-pilot-db` copies company/portal registry state into a disposable SQLite database and
removes historical jobs, AI analyses, observations, scan attempts and scan runs. This ensures the
pilot report contains only jobs discovered in that pilot.

## End-to-end path

`official portal -> raw discovery -> PENDING_AI -> JobAnalyzer -> CYBER/NON_CYBER -> report`

The pilot does not yet delete NON_CYBER technical queue rows. The product view/report exposes the
CYBER subset; destructive pruning remains deferred until the pipeline has been validated on real
runs.
