# Decision 0002: Human-curated target employers and manual tiers

- Status: Accepted
- Date: 2026-09-02

## Decision

The operational universe is an explicit, human-curated list of **target employers** rather than an
automatically ranked subset of the 11,798-cluster discovery universe.

The term `target_employer` is preferred to `target_company` because relevant employers may include
international/public organizations such as ENISA, NATO, ESA or the ECB.

No algorithm may automatically add, remove, rank, promote or demote employers. The list is versioned
product configuration and can change only through a conscious product decision.

## Inclusion criteria

An employer can be included when we judge it materially useful for cybersecurity career monitoring for
at least one of these qualitative reasons:

1. global technology / cloud / AI / semiconductor leader;
2. cybersecurity product/category leader;
3. major finance / payments / market-infrastructure employer;
4. aerospace / defence / space leader;
5. automotive / embedded / mobility leader;
6. energy / utilities / critical-infrastructure leader;
7. telecom / networking leader;
8. industrial / robotics / advanced-technology leader;
9. major consulting / security-services employer useful for opportunity or skill intelligence;
10. important public/international cyber employer;
11. exceptional employer that is clearly valuable even if it does not fit a category above.

The criteria are **guidelines for human judgment**, not a scoring formula.

## Tier semantics

Tier means how costly it would be for this project to discover an opportunity late; it is **not** a
worldwide company-importance ranking.

- `S`: must-not-miss employer; low desired discovery latency.
- `A`: highly valuable employer; systematic monitoring.
- `B`: useful opportunity / market-intelligence employer; lower urgency.

There is intentionally no Tier C. If an employer matters too little for Tier B, it should normally remain
outside the operational target set rather than recreating the 11,798-company universe.

## Implementation shape

Versioned config:

```yaml
employers:
  - name: Google
    tier: S
    enabled: true
    primary_category: global_tech_cloud_ai
    inclusion_reasons:
      - global_technology_leader
      - large_security_organization
      - high_cv_signal
```

`inclusion_reasons` are explanatory metadata only; they are never converted into an automatic score.

## Brand / parent rule

The operational set may retain meaningful employer brands even when a corporate parent owns them, but
portal scanning must remain deduplicated. Parent/brand metadata must never cause source job labels to be
lost.

Examples current as of this decision:

- CyberArk -> Palo Alto Networks;
- Wiz / Mandiant -> Google / Alphabet;
- Splunk -> Cisco;
- Recorded Future -> Mastercard.

## Why

- Automated rankings create false precision and hide value judgments inside arbitrary weights.
- The project has a specific career-research objective, not a universal employer-ranking objective.
- Explicit curation is auditable and easy to challenge together.
- Manual tiers can later control scan cadence without affecting whether a discovered cyber job is stored.

## Trade-offs / challenge

Manual curation can become stale. The mitigation is a small, reviewable, versioned config — not an
automatic ranking system. New high-value employers can be proposed at any time, but inclusion remains a
human decision.
