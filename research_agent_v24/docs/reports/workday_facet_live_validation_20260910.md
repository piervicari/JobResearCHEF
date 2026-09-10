# Workday facet live validation — 2026-09-10 (evidence collection only)

Scope: bounded facet-semantics probe. NOT a catalog completion attempt. No
claim about full-board coverage. Proof hook stays FALSE; capped
complete_snapshot=TRUE NOT enabled.

## Target + budget

- Tenant: Airbus Workday, `https://ag.wd3.myworkdayjobs.com/Airbus`
  (registry portal 5, scan_enabled). Why: JRC-validated adapter path
  (2026-09-08 wave: exact partials at page budget) and excluded from
  cohort-60 as a ~2000 board — the capped case under study.
- Wires: 6/15 (1 landing + 2 root + 2 children + 1 nested). All HTTP 200.
  Concurrency 1, retries 0, ~1.6 s pacing, plain urllib (no JRC DB code —
  zero production writes possible). No 403/429/challenge/auth-wall/
  redirect drift. Response sizes 13–38 KB.
- Queries: root `{}` @0 twice; `{jobFamilyGroup:[A]}` / `[B]` @0 (first
  two advertised values); nested `{jobFamilyGroup:[A], startDate:[v0]}` @0.

## Findings

1. ROOT FACETS: total=2000 exactly (cap CONFIRMED live). 8 dimensions:
   startDate(6), jobFamilyGroup(14), jobFamily(55), hiringCompany(55),
   workerSubType(6), FullPartTime(2), Reload_Classification(13),
   locationMainGroup(2, NESTED sub-groups locationCountry/locations).
   Value shape `{id, descriptor, count}` — opaque hash ids. No
   `locations` or `timeType` facetParameter on this tenant (JRC static
   keys 3–4 miss here; skip-on-absence handles it).
2. STABILITY (one repeat, seconds apart): dims, value ids, counts,
   ordering, and page-0 posting ids IDENTICAL. Weak (n=1) but clean.
3. APPLIEDFACETS: accepted; children totals 636 and 385.
4. NESTED: filters AND-combine (nested total 36 ≤ each parent universe).
5. ADVERTISED vs CHILD: 636==636, 385==385, nested 36==36 → 3/3 MATCH.
6. COUNT UNIVERSE: dimension sums EXCEED the cap (JFG 2558, startDate
   2710, FullPartTime 2756, workerSubType 2760) → counts reflect the TRUE
   universe (~2500–2700), not the capped 2000 set. True total > reported
   total: cap behaviorally confirmed. Reload_Classification sums to 390
   → partial dimension exists (C1 would correctly fire on it).
7. OVERLAP: PROVEN live — workerSubType sums (2760) exceed FullPartTime
   sums (2756) exceed JFG sums (2558); dimensions disagree on universe
   size, so overlap and/or no-value populations MUST exist somewhere.
   Child page-0 overlap c0∩c1 = 0 (weak, first pages only).
8. MISSING MEMBERSHIP: UNKNOWN (bounded probe cannot enumerate
   no-value jobs; Reload_Classification's 390-sum shows large
   no-value populations are real for some dimensions).
9. IDENTITY SHAPE: bullets lead with JR-ids (`JR10438527`); trailing
   grade labels (`Classe F12`) correctly ignored by JRC shape-first
   logic (20/25 bullets match; rest are grade text). No badge-first
   rows observed on this tenant.
10. CAP/WRAP: total==2000 + true≈2600 confirms the cap; offset wrap NOT
    tested (no deep paging in budget); subdivision coverage NOT proven.

## Classification: NEEDS_MORE_EVIDENCE

Promising (stability + 3/3 count matches + true-universe counts) but
insufficient: one tenant, one time-point, no missing-membership proof,
no wrap test, overlap confirmed. The C1/C2 structural poisoning stays
as-is. A future proof rule must additionally handle tenant-specific
facet vocabs (Airbus lacks `locations`/`timeType`) and partial
dimensions (Reload_Classification-class).

## Proven / Unknown

PROVEN: cap exists (2000 < true ~2600); appliedFacets accepted + AND;
3/3 advertised==child; short-term stability; overlap exists; bullets
compatible with JRC identity. UNKNOWN: value-list exhaustiveness;
no-value populations per dimension; wrap behavior; count semantics
under churn; any second tenant.
