# Decision 0009: Scan higher-priority company tiers more frequently

- Status: Accepted principle / cadence TBD
- Date: 2026-09-02

## Decision

Manual company tiers should influence scan cadence: Tier S companies are checked more often than Tier A,
and Tier A more often than Tier B.

Exact frequencies are intentionally not frozen until real scan behavior, update rates and source limits are
observed.

## Why

- High-value companies deserve lower discovery latency.
- Uniform cadence wastes requests on slow-changing employers and can increase rate-limit risk.
- The benefit of sub-hourly polling is likely small for job applications; frequency should remain bounded.

## Initial candidate cadence for testing (not final)

```text
Tier S: ~3 scans/day
Tier A: ~1 scan/day
Tier B: ~2-3 scans/week
```

## Future extension

A simple seasonal boost may temporarily increase cadence for companies with evidence-backed internship
opening windows. This is deferred until Program Intelligence exists.
