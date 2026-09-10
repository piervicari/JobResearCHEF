# Workday completeness-proof evidence — 2026-09-10

35/35 ATS wires. Concurrency 1, retries 0, ≥1.4 s pacing, standalone
scripts (zero DB writes), no 403/429/challenge. Proof hook stays FALSE;
no bodies committed (IDs/counts recorded only).

## B — Airbus wrap: WRAP_PROVEN

Offsets (page 20): 0 → total 2000, 20 jobs; 1980 → total 0 (!), 20 jobs;
2000 → total 2000, IDs byte-identical to offset 0; 2020 → identical to
offset 0; 2000-repeat → deterministic. Pagination at/above 2000 wraps
(modulo-style) instead of erroring or emptying. The total=0 past page 1
is live confirmation of the pinned-canonical-total design JRC already
implements. 6 wires.

## C — Proofpoint coverage: INCONCLUSIVE (with exact bounds)

Root fully enumerated with pinned totals: 145/145 unique IDs (8 pages;
naive total-driven stopping would quit at page 2 — process lesson, JRC
code already handles this). Top-2 JFG branches fully enumerated:
Sales 60/60 advertised, Eng 35/35, both ⊆ root. Remaining 9 branches:
totals == advertised observed, IDs not enumerated (budget). Union
question therefore unresolved: IF the 9 unverified branches reconcile
like the top 2, union = 142 < 145 → non-exhaustive; without their IDs
this is arithmetic, not proof. Root-only sample payloads carry no facet
membership fields (title/locations/bullets only), so listing data cannot
distinguish no-value jobs from hidden values. Gap stays
OBSERVED_FACET_COVERAGE_GAP. 23 wires (16 + 7 redo).

## D — Second capped tenant: FOUND (minimal validation)

NVIDIA Workday (`nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite`,
same wd5 backend as the Eightfold 2686-board): root total = 2000
exactly. Facets: jobFamilyGroup(15), workerSubType(6), timeType(2),
locationMainGroup(3). Boundary/child checks deferred (no budget left).
2 wires.

## E — Semantics

FILTERABLE: proven (every appliedFacets accepted, 15/15 across waves).
USEFUL_FOR_EXPANSION: proven (children return proper subsets of root).
EXHAUSTIVE_FOR_PARENT: not proven anywhere (Proofpoint partial).
EXCLUSIVE_PARTITION: not proven anywhere. A dimension may be
filterable+useful while exhaustive/exclusive stay false — the
capability split holds.

## F — Proof design (not implemented)

Shape: capped parent → discovered capability → prove values exhaust the
parent → traverse all → every child safe → reconcile counts/totals →
recurse for capped children → union+dedup → MAY complete. Challenge
results: (a) parent total capped ⇒ sums can only REFUTE (C1), never
confirm; (b) sibling/small-tenant observations don't transfer
(tenant-specific vocabs); (c) no Workday no-value bucket observed;
(d) overlapping-but-exhaustive dims could prove only via
union==parent, which needs wrap-absence + full enumeration — circular
without an independent exhaustiveness primitive. Remaining blocker: a
bounded per-tenant exhaustiveness test with no verified implementation
yet. Hook stays FALSE.

## Capability layer review

Still valid, no code change. C1's trigger shape (142 < 145) matches the
live gap exactly. Wires: B6 + C23 + D2 + Credo-included = 35/35.
