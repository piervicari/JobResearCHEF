# Workday cap guard + facet-subdivision design — 2026-09-09

PHASE A IMPLEMENTED. PHASE B IMPLEMENTED 2026-09-09 (static recursive
facet subdivision in `sources/ats/workday.py`, offline-tested only — no
live validation yet). PHASE C DESIGNED ONLY — not implemented.
Zero live wires used; evidence is repository code + vendored Stapply
ats-scrapers v0.3.0 (`external_reuse_audit/vendor/ats-scrapers`) + synthetic
fixtures. Invariant: ALL locations and ALL categories in scope — facets affect
HOW/ORDER, never WHETHER a job is ingested.

## Phase A — cap guard (IMPLEMENTED)

Trigger: canonical (page-1 pinned) Workday `total ==
WorkdayAdapter.PROVIDER_RESULT_CAP (2000)`.
Behavior: `complete_snapshot` forced FALSE + `CAPPED_TOTAL_WARNING`;
jobs still parsed/persisted with existing requisition-shape identity.
A genuine 2000-job board conservatively reads BOUNDED (accepted:
false-incomplete beats false-complete). Uncapped totals (< 2000, 0,
> 2000) behave exactly as before. Provider-general: one constant + one
helper (`_is_suspicious_capped_total`), no company names, no magic numbers
elsewhere. Regression tests: uncapped-44 → TRUE; capped-2000 fully
traversed → FALSE + warning + requisition ids intact; budget-capped scan →
FALSE; badge-label identity fallback intact.

## Stapply Workday strategy (as studied, not copied blindly)

- Cap detection: per-query `total == 2000` (`QUERY_TOTAL_CAP`); uncapped
  tenants (e.g. ~22K) report real totals and paginate cleanly. Past
  offset 2000, pagination WRAPS to page 1 — silent duplication risk.
- Available facets: `appliedFacets` server filter; `facets[]` in every
  response carries `{facetParameter, values[{id, count}]}` with TRUE counts.
- Subdivision order: `jobFamilyGroup` → `timeType` → `locations` →
  `workerSubType`, then dynamic fallback to highest-cardinality remaining
  facet; facets with <2 values or already applied are skipped.
- Recursion: `_exhaust_query(applied_facets, depth)`; uncapped branch →
  normal offset fan-out; capped branch + unused facets → subdivide;
  capped + no facets left → accept ≤2000 from that leaf and stop.
- Dedup: `ats_id or url` set-absorb across ALL branches (overlap-safe;
  `workerSubType` is multi-tag so branch sums exceed the total by design).
- Termination: `MAX_SUBDIVISION_DEPTH = 4`; per-branch offset fan-out under
  a shared semaphore; bounded loss is explicit, never silent.

## Phase B — JRC static subdivision (IMPLEMENTED 2026-09-09, offline only)

Implemented as designed, with two recorded deviations:
- Partial jobs are ALWAYS merged before a branch reports failure (budget,
  empty page, fetch error, skipped postings) — jobs collected before the
  problem persist; only the completion flag goes FALSE.
- Union-level job-cap: `>` cap truncates + FALSE; `==` cap keeps all rows
  but still FALSE (conservative; a full union at exactly the record cap
  cannot prove absence of truncation).
Root page-0 doubles as cap/facet probe (no extra wire); uncapped request
sequences and warning texts are byte-identical to pre-Phase-B behavior.

Root query (empty `appliedFacets`, as today) → read `total` + `facets[]`.
If `total != 2000`: today's pagination unchanged. If capped: partition on
`jobFamilyGroup` first (Stapply's proven default), then per-branch
`timeType` → `locations` → `workerSubType` ONLY for branches still capped.
Traverse ALL values of the chosen dimension at every level (ALL locations,
ALL categories — no pruning). Union with `source_job_id or apply_url`
dedup (JRC identity, NOT Stapply's `bulletFields[0]`). Reuse existing
concurrency-1 / retries-0 / wire-budget machinery per branch; any branch
hitting budget or erroring fails that branch explicitly.

## Phase C — dynamic facet selection (DESIGNED, deferred)

Do NOT build an optimizer yet. When Phase B ships and real capped boards
are observed, the planner may choose the partition dimension from live
`facets[].values[].count` preferring: fewest branches, fewest
still-capped branches, fewest expected page requests, least overlap —
in that priority order, with the static Phase-B order as the default when
counts are missing. Graduate Phase B → C ONLY on measured evidence that
static order wastes branches on real boards.

## Completeness semantics (enforced)

`complete_snapshot = TRUE` iff (a) uncapped catalog reached natural end,
OR (b) capped catalog was partitioned AND every required branch reached
complete natural end AND subdivision coverage is proven. (b)'s coverage
proof is currently IMPOSSIBLE from offline evidence (see Coverage
hardening below) — so capped roots stay FALSE while keeping all
discovered jobs. No absence-based closure from an incomplete scan
(existing lifecycle rule unchanged: closure requires TRUE).

## Coverage hardening (2026-09-09) — subdivision discovers, never completes

Finding: traversing every advertised facet value does NOT prove a capped
root was covered. Evidence (vendored Stapply v0.3.0 + payload semantics):
- Stapply performs NO coverage check — union-absorb only, completeness
  merely asserted in a comment ("the union covers the full set").
- Facet value lists carry no exhaustiveness marker (no per-facet total,
  no truncation flag) — truncated lists are indistinguishable from
  complete ones offline.
- Jobs may lack a value in the chosen dimension (site-less-style records
  exist; no-value postings are plausible and unrefuted).
- Advertised counts' universe is unknown (capped-2000 set vs true set);
  `sum(counts) == root.total` is UNSAFE as a rule (root total is capped).
- workerSubType demonstrably OVERLAPS (Stapply's own comment: multi-tag,
  sums exceed total) — no dimension gets exclusivity by default.

Rules implemented (all fail toward FALSE, never toward TRUE):
- C1 proven-incomplete: sum(advertised counts, chosen dimension) <
  parent total → COVERAGE_INCOMPLETE (overlap can only inflate sums).
- C2 count contradiction: cleanly paginated child total != advertised
  count for that value → informational mismatch warning.
- Proof hook `_subdivision_coverage_proven()` returns False with the live
  evidence gate documented in-code (value-list stability, zero no-value
  jobs, full advertised-vs-recovered reconciliation, wrap-absence proof).
- Overlap (e.g. identical jobs across branches) dedups correctly AND
  counts against partition-completeness.

## Live facet evidence (2026-09-10, Airbus portal 5, 6 wires)

Full report: `docs/reports/workday_facet_live_validation_20260910.md`.
Classification: NEEDS_MORE_EVIDENCE. Proven: strong evidence of capped
semantics (reported 2000 vs ~2600 implied universe); appliedFacets
accepted and AND-combine; 3/3 advertised==child totals
(636, 385, nested 36); short-term repeat stability; non-partition
semantics indicated;
(dimensions disagree on universe size: 2558 vs 2756 vs 2760);
Reload_Classification (sum 390) proves partial dimensions are real;
bullets compatible with JRC shape-first identity. Unknown: value-list
exhaustiveness, no-value populations, wrap behavior, second tenant.
Tenant facet vocab DIFFERS from static keys (no `locations`/`timeType`
facetParameter on Airbus; nested locationMainGroup) — skip-on-absence
is the correct behavior; one tenant is not enough to redesign the
dimension list. Proof hook stays FALSE; C1/C2 structural poisoning stays.

## Multi-tenant validation (2026-09-10, +Brunello/Proofpoint, 12 wires)

Full report: `docs/reports/workday_facet_multitenant_validation_20260910.md`.
Static tuple portability: PARTIAL (jobFamilyGroup + workerSubType common
3/3; timeType tenant-specific-or-degenerate; `locations` absent
everywhere — nested groups instead). Advertised==child 9/9 incl. nested
AND-combines; repeat stability holds for ids+counts (not tie order).
PARTIAL_COVERAGE proven live once (Proofpoint JFG 142/145 — missing
membership is real). Cap stays STRONG_EVIDENCE_NOT_PROVEN (no B-proof:
no exhaustive+exclusive dim >2000; A refused on budget; wrap untested).
Capability model DESIGNED (payload-discovered eligibility, per-tenant
classes, static preference order kept) — NOT implemented. Proof hook
unchanged (FALSE).

## Controlled live-validation budget (designed, NOT activated)

Current real defaults (`config/settings.yaml` + `ScannerSettings`): page
20/Workday, max_pages_per_portal 30, max_requests_per_host_per_run 30,
max_requests_per_run 500, max_jobs_per_portal 500 (bulk 5000),
per-domain concurrency 1, pacing 1.0 s. A capped Workday traversal does
NOT fit: 2000 jobs need ~101 wires on one host.
No global change and no new plumbing: `settings.scanner.model_copy()`
(per-run override precedent in `scan_pilot_command`) plus the
`RESEARCH_AGENT_` env prefix already express a single-portal validation
profile. Proposed profile (future run only): concurrency 1, retries 0,
1.0 s+ throttle, explicit per-run host cap ≥ estimated wires + margin,
explicit run cap, explicit page/job caps, single Workday portal,
disposable DB. Cost estimates (catalog wires, +1 landing):
ordinary pagination — 2000 ≈ 101, 5000 ≈ 251, 10000 ≈ 501;
subdivision ≈ ordinary + per-branch rounding/probe overhead (small when
branches partition cleanly; deeper nesting adds probes per capped level).
Subdivision is NOT a wire-saving measure — it buys completeness, bounded.
