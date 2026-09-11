# Source scan strategy — capability audit (2026-09-09)

Principle: TIER decides WHEN a company is scanned (Tier-S = daily, never
reduced for network reasons). SOURCE capabilities decide HOW. Evidence:
adapter code + cohort 15/60 live bodies + 5 audit probes (2026-09-09).

## Provider table

Legend: daily strategies NATIVE_DELTA / SAFE_WATERMARK / LIGHTWEIGHT_SINGLE_SHOT /
FULL_SINGLE_SHOT / FULL_PAGINATION_REQUIRED / UNRESOLVED. Detail: INLINE_REQUIRED / SELECTIVE_DETAIL /
NO_DETAIL_NEEDED / UNKNOWN. Costs = catalog wires (excl. detail), retries 0.

### Workday — FULL_PAGINATION_REQUIRED / SELECTIVE_DETAIL
- Catalog: landing bootstrap (tenant/siteId regex) + POST
  `{origin}/wday/cxs/{tenant}/{site}/jobs` `{limit, offset}`. Page size 20
  (proven; limit=50 and limit=100 → HTTP 400, so 20 is the safe max known).
- Total authoritative on page 1 only; offset sequence exact; no date/update
  filters, no sort control, ordering unspecified → watermark UNSAFE.
- Catalog rows carry NO description (title/externalPath/bullets/locations/
  postedOn only); requisition = shape-matched bullet else externalPath.
- Costs: 1 + ceil(N/20): @100 = 6, @500 = 26, @1000 = 51, @3600 = 181.
  Payload LOW per page (~4–9 KB). Detail: 1 GET per selected job.
- Cap guard (IMPLEMENTED 2026-09-09): canonical total == 2000 forces
  `complete_snapshot = FALSE` + warning (provider cap; upstream may hold
  more; past offset 2000 wraps).
- Phase-B static facet subdivision (IMPLEMENTED 2026-09-09, offline only):
  capped root partitions over jobFamilyGroup → timeType → locations →
  workerSubType via `appliedFacets`, all values traversed, JRC identity
  union dedup, partial jobs always kept. HARDENED 2026-09-09: subdivision
  expands discovery but NEVER completes a capped root offline (coverage
  unprovable: no exhaustiveness marker, possible no-value jobs, unknown
  count universe, workerSubType overlaps, Stapply checks nothing) —
  capped roots stay FALSE with INCOMPLETE/MISMATCH/UNPROVEN warnings.
  CAPABILITY LAYER 2026-09-10 (offline only): dimensions discovered from
  the live payload (`WorkdayFacetCapability`: expansion-usable vs
  proof-eligible split; PARTIAL/UNKNOWN stay usable for discovery;
  nested groups exposed, never flattened; static preference, no
  optimizer). Proof hook stays FALSE.
  LIVE 2026-09-10 (Airbus, 6 wires): strong evidence of capped semantics
  (2000 reported vs ~2600 implied universe),
  appliedFacets AND-combine, 3/3 advertised==child, non-partition
  semantics indicated,
  tenant facet vocab differs (no locations/timeType keys) — proof still
  NEEDS_MORE_EVIDENCE, hook stays FALSE. MULTI-TENANT 2026-09-10
  (+Brunello 47, +Proofpoint 145, 12 wires): static tuple PARTIAL
  (JFG+workerSubType common; locations absent everywhere); advertised==
  child 9/9; Proofpoint JFG 142/145 is an OBSERVED_FACET_COVERAGE_GAP
  (cause unresolved: missing membership, truncated values, or other
  semantics);
  cap STRONG_EVIDENCE_NOT_PROVEN; capability layer implemented, not
  designed-only;
  Live evidence: `docs/reports/workday_facet_live_validation_20260910.md`.
  PROOF WAVE 2026-09-10 (35/35 wires): WRAP_PROVEN on Airbus (2000 == 0
  IDs); Proofpoint root 145/145 with top-2 branches reconciled, union
  INCONCLUSIVE; second capped tenant FOUND (NVIDIA 2000); proof shape
  designed, exhaustiveness primitive still missing, hook FALSE.
- Closure: only when a full traversal completes (complete_snapshot TRUE).

### Greenhouse — LIGHTWEIGHT_SINGLE_SHOT / SELECTIVE_DETAIL
- Catalog: single GET `boards-api.../boards/{token}/jobs?content=true`,
  authoritative-complete (response IS the catalog → closure-safe daily).
- Lightweight PROVEN live 2026-09-09: `?content` omitted returns the same 39
  jobs with id/title/location/absolute_url/metadata/requisition_id/
  first_published/updated_at and NO content (37 KB vs full). Detail
  `/jobs/{id}` PROVEN live (full content + departments/offices).
- Ordering NOT newest-first (proven on saved bodies) → watermark UNSAFE.
  ETag present + fetcher 304 support → conditional revalidation saves bytes
  (still 1 wire). No pagination params, no filters.
- Costs: 1 wire at ANY board size (@100/@500/@1000/@3600 = 1). Payload scales
  with board (~1 KB/job lightweight; full ~10×). Detail: 1 GET per triaged job.
- Mega-board implication: SpaceX/Anduril >20 MB bodies came from full-content
  fetch; lightweight catalog (~2 MB @2000 jobs) fits the existing guard.
  Do NOT raise the 20 MB limit (technically possible, architecturally inferior).
- Closure: safe daily (complete_snapshot TRUE every scan).

### Eightfold/PCSX — FULL_PAGINATION_REQUIRED / SELECTIVE_DETAIL
- Catalog: GET `.../api/pcsx/search?domain=&start=&hl=`, offset pages of
  exactly 10. `limit=100` PROVEN ignored (10 returned) → 10 is the effective
  max known. Total (`data.count`) drifts live (2686→2605 observed).
- No date/update filters proven; `sortBy` field exists but semantics unproven
  → watermark UNSAFE. Catalog has NO description. Same-host detail PROVEN.
- Costs: ceil(N/10): @100 = 10, @500 = 50, @1000 = 100, @3600 = 360.
  Payload LOW per page (~9 KB). Most expensive daily family at scale.
- Closure: only on full traversal (never achieved live; budget-capped).

### Oracle Recruiting Cloud — FULL_PAGINATION_REQUIRED / SELECTIVE_DETAIL
- Catalog: landing + GET `recruitingCEJobRequisitions?finder=findReqs;
  siteNumber=,limit=200,offset=` (limit=200 proven live). Total-driven adaptive
  pagination (offset += received). Catalog has ShortDescriptionStr (partial).
- No update filters / sort control proven → watermark UNSAFE. Detail ById
  live-proven (CAN2). SSO-walled tenants (JPMorgan) are hard stops.
- Costs: ~1 landing + ceil(N/200): @100 = 2, @500 = 4, @1000 = 6, @3600 = 19.
- Closure: only on full traversal.

### Lever — FULL_PAGINATION_REQUIRED / NO_DETAIL_NEEDED
- Catalog: GET `api.lever.co/v0/postings/{slug}?mode=json&skip=&limit=100`,
  ends on short page, no total. Description assembly inline COMPLETE.
- No filters/sort proven → watermark UNSAFE (short-page end only proves the
  tail observed, not absence of churn behind).
- Costs: ceil(N/100): @100 = 1–2, @500 = 5, @1000 = 10, @3600 = 36.
- Closure: on natural short-page end.

### Ashby — FULL_SINGLE_SHOT / NO_DETAIL_NEEDED
- Catalog: single GET `posting-api/job-board/{board}?includeCompensation=true`,
  descriptionHtml inline COMPLETE (781-row board proven 1 wire).
- Same mega-board caveat class as Greenhouse (unbounded single response);
  lightweight variant not yet probed (UNKNOWN — 1-probe follow-up suffices).
- Costs: 1 wire any proven size. Closure: safe daily.

### SmartRecruiters — FULL_PAGINATION_REQUIRED / SELECTIVE_DETAIL
- Catalog: GET `{company}/postings?limit=&offset=` (100/page),
  `totalFound` terminal. Catalog description partial/empty.
- No filters/sort proven → watermark UNSAFE. Detail endpoint proven by shape
  only (no live detail yet — recorded gap).
- Costs: ceil(N/100): @100 = 1, @500 = 5, @1000 = 10, @3600 = 36.
- Closure: on total-guarded natural end.

### Teamtailor / Workable — FULL_SINGLE_SHOT / NO_DETAIL_NEEDED
- Single GET (`/jobs.json` / widget `?details=true`), inline complete
  descriptions. Costs: 1 wire. Closure: safe daily. Thin tenant counts.

### SuccessFactors RMK — UNRESOLVED / UNKNOWN
- HTML `startrow` pages, `sortColumn=referencedate desc` configured but
  completion never achieved live within budget. Watermark UNSAFE (unproven
  stability + HTML scraping). Needs its own bounded validation before any
  daily-strategy claim.

### Google custom RPC — LIGHTWEIGHT_SINGLE_SHOT (low evidence) / UNKNOWN
- Probe-scoped single-shot per decisions 0049/0050. Re-audit before daily use.

### Phenom / Avature / Radancy — as-implemented / UNRESOLVED
- Adapters exist; no live scale evidence. Bounded as-implemented scans only.

## Cost summary (catalog wires, daily)

| Jobs | WD | GH-light | 8fold | Oracle | Lever | Ashby | SR |
|---|---:|---:|---:|---:|---:|---:|---:|
| 100 | 6 | 1 | 10 | 2 | 2 | 1 | 1 |
| 500 | 26 | 1 | 50 | 4 | 5 | 1 | 5 |
| 1000 | 51 | 1 | 100 | 6 | 10 | 1 | 10 |
| 3600 | 181 | 1 | 360 | 19 | 36 | 1 | 36 |

Detail (only for triaged CYBER/UNCERTAIN): 1 request/job on WD/GH/8fold/Oracle/SR.

## Architecture direction (designed, NOT implemented)

TIER → FREQUENCY (S = daily, mandatory) → SOURCE CAPABILITY → NETWORK STRATEGY
→ lightweight catalog → DB identity/delta (payload_sha change requeues
PENDING_AI — already implemented) → LLM TRIAGE on cheap metadata only
(title/department/location) → CYBER/UNCERTAIN → selective detail → full AI;
NON_CYBER stays a lightweight stub forever. No title-substring hard filters.

Storage: SourceJob already splits raw_* vs detail_* with dual hashes
(payload_sha256 / detail_payload_sha256); no migration needed for stubs.
Smallest future change if any: separate discovery-hash from description-hash
so description-only edits don't retrigger triage (optional, unproven need).

Closure: bounded/incremental scans MUST NOT close (already enforced:
lifecycle skips closure unless complete_snapshot TRUE). Single-shot families
reconcile daily for free; paginated families need periodic full-traversal
reconciliation (cadence TBD, does NOT replace daily discovery).

## Evidence levels / unknowns

Proven live 2026-09-09 (5 wires): GH lightweight fields + GH detail +
WD limit100→400 + WD limit50→400 + PCSX limit100-ignored.
Unproven: GH conditional-304 round-trip; Ashby lightweight variant;
SR live detail; RMK completion; any watermark safety anywhere (all UNSAFE).
P1 impact: SpaceX/Anduril dissolve under GH-light; site-less WD + SentinelOne
are registry corrections; SSO walls stay hard stops.

## Stapply + facet audit (2026-09-09, code-read, 0 ATS wires)

Full evidence: `docs/reports/stapply_facet_integration_audit_20260909.md`.
Workday is the only PROVEN TRUE_FACET family among the providers audited so
far (`appliedFacets` + per-value counts);
Eightfold is SERVER_FILTER_ONLY (query/location/sort, start-only in JRC
spec); GH/Lever/Ashby need NO subdivision (single-shot complete).
Phase-B static Workday subdivision IMPLEMENTED 2026-09-09 (offline only,
no live validation yet); dynamic planning NOT implemented. Facets
partition/order/metadata only — never ingest-or-skip. All locations and
all categories stay in scope.
