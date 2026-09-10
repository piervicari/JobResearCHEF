# Workday facet multi-tenant validation — 2026-09-10

Tenants (all JRC-validated, no discovery): Airbus portal 5 (stored 09-10
measurements, 0 new wires), Brunellocucinelli portal 511 (small fashion,
total 47), Proofpoint portal 265 (mid security, total 145).
Wires: 12/18 (6+6), all HTTP 200, concurrency 1, retries 0, ~1.3 s pacing,
standalone urllib (zero DB writes). No 403/429/challenge/drift.

## Vocabulary comparison

| dimension | Airbus (~2600) | Brunello (47) | Proofpoint (145) | class |
|---|---|---|---|---|
| jobFamilyGroup | 14, sum 2558 | 5, sum 47 | 11, sum 142 | COMMON |
| workerSubType | 6, sum 2760 | 4, sum 47 | 4, sum 145 | COMMON |
| jobFamily | 55 | 22, sum 47 | — | TENANT_SPECIFIC |
| hiringCompany | 55 | — | — | TENANT_SPECIFIC |
| timeType | — (FullPartTime×2 instead) | — | 1 value (degenerate) | TENANT_SPECIFIC |
| locations | — (nested locationMainGroup) | — (nested) | — (nested) | ABSENT→NESTED |
| startDate / Reload_Classification | present | — | — | TENANT_SPECIFIC |

Static tuple portability: PARTIAL. jobFamilyGroup + workerSubType common
(3/3); timeType vendor-specific-or-degenerate (missing/1-value/renamed);
`locations` absent on ALL observed tenants (nested group pattern instead).
Airbus failure mode CONFIRMED: after jobFamilyGroup, dims 2–4 all miss —
subdivision still paginates children (safe direction) but can never
recruit a second partitioning axis there.

## Filter/count checks (MATCH 9/9)

Children accepted everywhere; nested filters AND-combine (3/3: 36, 13,
58 all == advertised). Advertised==child: Airbus 636/385, Brunello
42/2, Proofpoint 141/2. Repeat stability: ids+counts stable (Airbus,
Proofpoint); Brunello swapped two tied (2,2) values → ordering NOT
guaranteed for ties. No MISMATCH observed.

## Partition / overlap / missing values

- PARTITION_CANDIDATE (single-tenant only): Brunello JFG/jobFamily/
  workerSubType (sums exactly 47); Proofpoint workerSubType/timeType
  (sums exactly 145). Candidate ≠ proven (exclusivity untested).
- PARTIAL_COVERAGE (live): Proofpoint jobFamilyGroup sums 142 vs total
  145 → OBSERVED_FACET_COVERAGE_GAP. Possible causes remain unresolved:
  missing membership, truncated facet value list, or other Workday
  semantics. Do NOT claim missing membership proven.
- OVERLAPPING: Airbus dimension sums disagree (2558/2756/2760) →
  non-partition semantics indicated; exact cause (overlap vs
  missing-value membership) unresolved. Child page-0 overlaps 0 (weak).
- UNKNOWN: value-list exhaustiveness everywhere; wrap mechanics.

## Cap evidence — STRONG_EVIDENCE_NOT_PROVEN (unchanged)

No tenant besides Airbus sits at 2000. Option B fails: no dimension
with defensible exhaustive+exclusive semantics exceeds 2000
(FullPartTime 2756 is suggestive but exclusivity/exhaustiveness
unproven). Option A (100+ wires for >2000 unique IDs) refused on
budget. Option C (wrap) untested.

## Capability model (design, NOT implemented)

WorkdayFacetCapability per live payload, no static assumptions:
{facet_parameter, descriptor, n_values, counts[], nested_subgroups[],
coverage_class ∈ {PARTITION_CANDIDATE, OVERLAPPING, PARTIAL_COVERAGE,
UNKNOWN}, usable_for_expansion, proof_eligible}. Expansion rule:
filterable AND n_values ≥ 2 — usable even when PARTIAL/UNKNOWN
(discovery ≠ proof). proof_eligible stays FALSE for capped catalogs.
Subdivision discovers dimensions from the payload in
a PREFERENCE order (today's static tuple first) and skips absent/
degenerate/unfilterable ones (PARTIAL/UNKNOWN stay usable for expansion). Coverage classes are per-tenant observations,
recomputed per scan — never cached theorems. Counts-based selection
stays Phase C.

## Static Phase-B impact

Code needs NO emergency fix: skip-on-absence already degrades
gracefully (Airbus resolves via jobFamilyGroup alone; coverage stays
FALSE correctly). Exact failure mode documented above. Dynamic
dimension discovery is the designed next step, not a hotfix.

## Unknowns / next

Exhaustiveness, no-value enumeration, wrap proof, second capped tenant,
count semantics under churn. Next: implement payload-discovered
dimension eligibility (capability layer, still static preference order,
still never completes capped roots) — NOT executed here.
Proof hook unchanged (FALSE).
