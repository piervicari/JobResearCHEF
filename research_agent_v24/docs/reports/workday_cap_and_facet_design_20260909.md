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

## Completeness semantics (future)

`complete_snapshot = TRUE` iff (a) uncapped catalog reached natural end,
OR (b) capped catalog was partitioned and EVERY required branch reached
complete natural end. FALSE if any branch hits page/job/wire budget, any
branch errors, subdivision cannot resolve the cap, or recursion depth is
exhausted with capped leaves remaining. No absence-based closure from an
incomplete scan (existing lifecycle rule unchanged: closure requires TRUE).
