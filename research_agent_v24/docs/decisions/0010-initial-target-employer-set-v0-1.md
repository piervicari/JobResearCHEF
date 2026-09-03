# Decision 0010: Initial target-employer set v0.1 and target-first resolution

- Status: Proposed for human review
- Date: 2026-09-02

## Decision / artifact

A first manually curated operational set has been materialized in:

- `data/target_employers/target_employers_v0_1.yaml`
- `data/target_employers/target_employers_v0_1_coverage.csv`
- `data/target_employers/target_employers_v0_1_report.md`

It currently contains 200 employers:

- 68 Tier S;
- 110 Tier A;
- 22 Tier B.

The list is intentionally marked `PROPOSED_FOR_HUMAN_REVIEW`; the names and tier boundaries are not
frozen until reviewed explicitly.

## Important result

Against the current runtime registry, the first draft already has:

- 60/68 Tier-S employers with a resolved + scannable portal;
- 157/200 employers overall with a resolved + scannable portal.

This means the immediate product bottleneck is **not** bulk resolution of the remaining 11k discovery
clusters. The higher-value work is:

1. scan the already-resolved target portals that have not yet had a successful run;
2. resolve the small target-only gap;
3. fix resolved target portals that the runtime currently marks non-scannable.

## Target-first portal resolution rule

Before another generic portal-resolution wave, resolution effort should operate on the curated target set,
in tier order:

```text
Tier S missing/broken
    -> Tier A missing/broken
        -> Tier B missing/broken
            -> only then generic discovery-universe expansion
```

This is a priority rule, not a permanent ban on expanding the discovery universe.

## Tier-S resolution-lite research

`data/target_employers/tier_s_portal_resolution_lite_v0_1.csv` contains researched portal candidates for
the currently uncovered/broken Tier-S targets, including OpenAI, Anthropic, Bloomberg, ENISA, NATO, ESA,
ECB and Check Point.

These candidates must be applied through a versioned registry change after runtime validation; the
research file itself does not pretend that the production DB has already changed.

If the seven currently missing Tier-S candidates validate successfully, **portal discovery coverage** for the
proposed Tier-S set becomes 68/68. This does **not** imply 68/68 runtime scannability: adapters/routes still
need to prove that they can enumerate jobs reliably.

## Why

The project objective is to become useful quickly. A curated Tier-S set with ~88% runtime portal coverage
has much higher immediate value than increasing global company resolution coverage from roughly 5% to 6%.
