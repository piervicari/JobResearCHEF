# 0011 — Core target membership is separate from scan cadence

**Status:** Accepted  
**Date:** 2026-09-02  
**Supersedes operational coupling in:** Decision 0009

## Decision

The initial 200 human-curated employers are all part of the **CORE cyber pilot target set**. For the pilot they may all be treated as Tier S / must-monitor employers.

However, **company membership/importance does not determine scan cadence**. Cadence is a separate operational policy that will be chosen after measuring actual request cost, portal reliability, update frequency and useful job yield.

No automated ranking decides whether an employer belongs to the core set.

## Rationale

The user prefers recall over aggressive prioritization and is willing to review a broad high-priority employer set. Artificially forcing 200 employers into S/A/B before the system has real operational measurements creates false precision.

At the same time, coupling "important employer" to "scan this portal three times per day" is unsafe: two equally valuable employers can have radically different ATS costs, pagination behavior, rate limits and publication frequency.

## Implementation implications

- `data/target_employers/target_employers_v0_2.yaml` is the active pilot set.
- All 200 employers have `monitoring_scope: core` and `tier: S` for pilot membership.
- No scheduler is enabled yet.
- Initial scans are manual/on-demand.
- A future cadence policy may assign different frequencies without changing employer membership.

Conceptually:

```text
CORE TARGET MEMBERSHIP (human decision)
                |
                v
         portal registry
                |
                v
SCAN CADENCE (operational decision)
  desired latency + measured cost/reliability/yield
```

## Trade-offs

### Accepted

- The label `S` loses discriminating power inside the 200-employer pilot.
- This is acceptable because the pilot needs a broad core set more than a prestige ranking.

### Rejected

- Automated employer scoring/ranking.
- Using market capitalization or company size as a scan scheduler.
- Blocking pilot use until a perfect S/A/B hierarchy is manually reviewed.

## Open questions

- After real scans, should cadence be static (e.g. 3/day, 1/day, 3/week) or activity-aware?
- Should seasonal internship windows temporarily boost cadence? Deferred until the basic scanner is useful.
