# Target employers v0.2 — cyber pilot core set

- Date: 2026-09-02
- Status: **ACCEPTED FOR CYBER PILOT**
- Human-curated employers: **200**
- Operational membership: **all 200 are Tier S / CORE**
- Tier is **not** coupled to scan cadence.

## Current portal coverage

- `resolved_scannable`: **157**
- `present_unresolved`: **17**
- `missing_to_resolve`: **16**
- `resolved_not_scannable`: **10**
- Core employers with a scannable portal but no successful scan yet: **103**

## Meaning of this version

This file freezes the initial **operational core set**, not a claim that these are the 200 objectively best employers in the world. Membership is a human product decision. The list may be manually revised, but no automated ranking can add/remove employers.

Scan cadence is intentionally separate. During the pilot, run scans manually/on demand. After measuring per-portal request cost, error rate, freshness and yield, assign cadence independently without changing core membership.

## Immediate implication

Do **not** continue generic Wave 7/8 resolution. First:

1. resolve/fix the curated core gaps;
2. migrate ingestion from deterministic semantic filtering to LLM cyber classification;
3. run the core set;
4. measure useful cyber-job yield and runtime behavior.
