# ATS Validation Matrix — ingestion reliability (evidence-based, no absolute guarantees)

Status enum: EXPERIMENTAL / VALIDATED_ONE_TENANT / MULTI_TENANT_VALIDATED /
PRODUCTION_SUPPORTED / NEEDS_EXTENSION / BLOCKED.
No numeric ratings. A status changes only on recorded evidence, never on
"tests pass" alone and never on a single live tenant for production support.

Evidence key: JRCAD = production adapter test; W2 = Wave-2 benchmark + probes;
W11 = Wave-1.1 probes + integration; CAN1/CAN2 = controlled canaries 2026-09-08;
EXT = external repo protocol reference (never runtime); FIX = saved fixture.

## Tier 1

### Workday
- Implementation: `sources/ats/workday.py` (name `workday`).
- Catalog: landing bootstrap + POST `{origin}/wday/cxs/{tenant}/{site}` jobs,
  body limit/offset (`page_size = 20` proven live), response `total`.
  Pagination: offset, total-guarded, total-change warning (code-read + JRCAD + live).
- Identity: adapter-native stable ID (requisition else externalPath;
  externalPath-derived detail addressing).
- Catalog description: none inline (live: 0/244 rows); `postedOn`, `locationsText` only.
  Catalog carries no `timeType`/`remoteType` live (W2.1 mapping unexercised on catalog).
- Detail: yes, GET CXS `{externalPath}` (Phase-3 renderer, live-proven 3/3 2026-09-08:
  0→332 / 0→4493 / 0→5960 chars, parser `workday_cxs_detail`, identity unchanged,
  employment hydrated `Full time`).
- Detail required: selective. Known tenants: 17 scan-enabled portals.
- Live validated: 3 (2026-09-08: brunellocucinelli 511 COMPLETE 44/44/44 exact,
  `complete_snapshot` TRUE; proofpoint 265 + airbus 5 exact partials 100/100/100,
  `complete_snapshot` FALSE at the 5-page budget cap; 4+6+6 wires; report
  `docs/reports/ats_validation_workday_20260908.md`).
- Empty tested: no. Pagination live: yes (3/5/5 pages, offsets exact, no
  repeat/skip/duplication). Multi-page live: yes.
- Live quirk: `total` authoritative on page 1 only, pages 2+ report `total: 0`
  (all 3 tenants); code-verified harmless (canonical total pinned page 1,
  later totals warn-only — workday.py:83-96), not a gate.
- Identity live: yes (distinct requisition IDs, 1 row each, detail preserves keys).
  Dedup live: yes. Completeness confidence: high for observed catalogs.
- Safety tested live: yes (21-wire budget respected, concurrency 1, retries 0,
  no 403/429/challenge, production DB untouched).
- Status: MULTI_TENANT_VALIDATED (3 tenants live 2026-09-08; report
  `docs/reports/ats_validation_workday_20260908.md`).
  NOT PRODUCTION_SUPPORTED: live empty-board + full-traversal proof on 100+
  boards still missing.
- Missing: empty-board observation; full traversal beyond the 5-page budget.
- Next: wave complete — next ATS recommended separately, not executed here.

### SmartRecruiters
- Implementation: `sources/ats/smartrecruiters.py` (name `smartrecruiters`).
- Catalog: GET `{company}/postings?limit=&offset=`, `totalFound` terminal
  (code-read + JRCAD + W2 triple agreement).
- Identity: posting id. Catalog description: partial/empty typical.
- Detail: yes, sanctioned cross-host `api.smartrecruiters.com/v1/companies/{slug}/postings/{id}`
  (Phase-3, offline-tested). Detail required: selective.
- Known tenants: 1 pure-SR portal (ZeroFOX) + 1 ServiceNow-flavored (armis).
- Live validated: 1 (CAN1 ZeroFOX). Empty tested: YES (HTTP 200, totalFound=0,
  valid schema, 1 wire). Pagination live: no (empty board).
- Detail live: no. Identity live: n/a (0 jobs). Dedup live: no.
- Completeness confidence: medium (contract solid, no non-empty live).
- Safety tested live: yes (1 wire, retries 0, clean stop).
- Status: VALIDATED_ONE_TENANT.
- Missing: non-empty board (only 1 SR portal in registry → multi-tenant
  blocked on tenant availability, documented, not worked around).
- Next: none available without source creation — do not force.

### Oracle Recruiting Cloud
- Implementation: `sources/ats/oracle.py` (name `oracle_recruiting_cloud`).
- Catalog: landing + GET `recruitingCEJobRequisitions?finder=findReqs;
  siteNumber=,limit=200,offset=` + `expand=requisitionList...`.
  Pagination: total-driven adaptive (offset+=received, empty-before-total
  fails, total-change → incomplete snapshot). limit=200 accepted live (W2).
- Identity: requisition Id; variant digest preserved, requisition migration
  explicitly deferred (W2.1). Detail never re-keys identity (CAN2 lineage).
- Catalog description: empty/partial typical. Detail: yes, ById endpoint
  (Phase-3, live-proven CAN2). Detail required: selective.
- Known tenants: 4 scan-enabled (141 danskebank, 145 edbz, 155 hdep, 158 honeywell).
- Live validated: 3 (Honeywell CAN2 + Danske Bank 141 + hdep 155, 2026-09-08;
  report `docs/reports/ats_validation_oracle_20260908.md`). Empty tested: no. Pagination live:
  single 200-page only. Multi-page live: no. Identity live: yes.
- Dedup live: yes (1 row per native id, CAN2). Completeness: medium
  (contract + adaptive guards + unit tests; no full traversal).
- Safety tested live: yes (concurrency 1, retries 0, budgets respected).
- Adapter-name defect found live (detail keyed `oracle`, real name
  `oracle_recruiting_cloud`) and fixed + regression-tested during CAN2.
- Status: MULTI_TENANT_VALIDATED (3 tenants live 2026-09-08: Honeywell CAN2
  + Danske Bank 141 + hdep 155; report `docs/reports/ats_validation_oracle_20260908.md`).
  NOT PRODUCTION_SUPPORTED: full-traversal + empty-board evidence still missing.
- Missing: empty-board observation; multi-page / total-variation episode live
  (guards unit-tested only); full-traversal proof.
- Next: none this phase (wave complete) — gaps listed above gate production support.

### Greenhouse
- Implementation: `sources/ats/greenhouse.py` (name `greenhouse`).
- Catalog: GET `boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true`,
  single request, authoritative-complete (code-read + JRCAD incl. bulk test +
  W2 identical-endpoint agreement).
- Identity: posting `id`. Catalog description: COMPLETE inline (content=true).
- Detail: none needed (expected 0 detail requests). Detail required: never.
- Known tenants: 12 scan-enabled (all cyber vendors).
- Live validated: 3 (2026-09-08: apiiro 160, chainguard 165,
  securityscorecard 170 — 1 wire each, all HTTP 200; API==unique==persisted
  7/7/7, 82/82/82, 39/39/39; 0 dups/malformed; report
  `docs/reports/ats_validation_greenhouse_20260908.md`).
- Empty: code + unit test (`jobs:[]` → complete + warning); live empty
  unobserved (no search performed per rule). Pagination: n/a
  (single request). Identity/dedup live: yes (distinct native ids, 1 row each).
  Content live: yes (per-portal min 2916 chars, requisition ids kept).
- Completeness: HIGH (single-response IS the catalog; full bodies re-parsed
  offline at 0 extra wires).
- Safety live: yes (3 wires total, retries 0, no signals, production DB untouched).
- Status: MULTI_TENANT_VALIDATED. NOT PRODUCTION_SUPPORTED: live
  empty-board observation is the single missing gate.
- Missing: one natural live `{"jobs": []}` (do not hunt).
- Next: wave complete — next ATS recommended: Lever. [SUPERSEDED 2026-09-08:
  Lever is MULTI_TENANT_VALIDATED; see Lever section.]

### Lever
- Implementation: `sources/ats/lever.py` (name `lever`, incl. jobs.eu host).
- Catalog: GET `api.lever.co/v0/postings/{slug}?mode=json&skip=&limit=`,
  paged (code-read + JRCAD + W2 live skiplimit probe 200 on sophos).
- Identity: posting `id` (existing value preserved). Catalog description:
  COMPLETE via assembly (`description` + `lists[]`, W2.1) + posted_at.
- Detail: none needed. Detail required: never.
- Known tenants: 2 scan-enabled (safe 214, watchguard 215 — the only
  adapter-served Lever portals in registry; both HEALTHY).
- Live validated: 2 (2026-09-08, 1 wire each, both HTTP 200, natural
  single-page end; API==parser==unique 18/18 safe, 24/24 watchguard;
  persisted 10+10 by pilot cap — E1 distinction, offline reparse proves
  full coverage at 0 extra wires; 0 dups/malformed; descriptions
  inline-complete min 1993 chars; 0 detail, 0 LLM; report
  `docs/reports/ats_validation_lever_20260908.md`).
- Empty live: not observed. Multi-page live: not observed (both boards <100).
- Completeness: HIGH for observed catalogs (exact accounting).
- Safety live: yes (2 wires, retries 0, production DB untouched).
- Status: MULTI_TENANT_VALIDATED (capped at the two canonical registry
  tenants — documented limitation). E1 closure 2026-09-08: saved bodies
  replayed through real `scan_portals` (cap 500, 0 wires) → 18/18 and
  24/24 persisted, `complete_snapshot` TRUE both. NOT PRODUCTION_SUPPORTED: live
  empty-board + live multi-page pagination still missing.
- Missing: natural empty board; multi-page episode.
- Next: wave complete — next ATS recommended separately, not executed here.

## Tier 2

### Eightfold (NVIDIA + Microsoft, declarative)
- Implementation: declarative specs `specs/nvidia.json` + `specs/microsoft.json`,
  exact bindings (no inference). Catalog: PCSX search page=10 + count.
- Identity: position_id via spec. Catalog description: empty (detail carries it).
- Detail: yes, `position_details` via bound spec, sanctioned cross-host
  (Microsoft → microsoft.eightfold.ai), full bridge fidelity, root-path
  semantics (Phase-3.1, offline-tested incl. Microsoft flow + evil-portal rejection).
- Detail required: selective (Eightfold rows carry no catalog description).
- Live validated: NVIDIA binding 1 (2026-09-08 bounded canary: 7 catalog wires
  starts 0–60, 10 each, total 2686 stable; API 70 = adapter 70 = persisted 70,
  0 dups/skipped, `complete_snapshot` FALSE at the 7-page cap — completeness
  unproven by budget design; same-host detail 1/1 0→2083 chars, parser
  `declarative_spec_detail`, identity preserved; 8-wire budget respected;
  report `docs/reports/ats_validation_eightfold_nvidia_20260908.md`).
  Microsoft binding 1 (2026-09-08 bounded canary: 7 catalog wires starts 0–60,
  10 each, totals 2179–2182 churning live; API 70 = adapter 70 = unique 66 =
  persisted 66 — 4 cross-page repeats from board churn deduped exactly once
  each, 0 skipped/missing/unexpected, `complete_snapshot` FALSE at the 7-page
  cap; sanctioned-host detail 1/1 0→6686 chars, parser
  `declarative_spec_detail`, identity preserved; 8-wire budget respected;
  report `docs/reports/ats_validation_eightfold_microsoft_20260908.md`).
- Registry note: production registry holds no portal matching either binding
  (NVIDIA 443 / Microsoft 187 serve generic HTML) — bound rows seeded in
  disposable DBs only. Empty-board live: no. Pagination live: yes (both).
- Identity live: yes (numeric `id`, 1 row each incl. under Microsoft churn).
  Catalog description: none (declared). Detail live: yes (both bindings).
- Safety tested live: yes (8+8 wires, concurrency 1, retries 0, no signals,
  production DB untouched).
- Status: MULTI_TENANT_VALIDATED (NVIDIA + Microsoft bindings live 2026-09-08;
  protocol/binding validity — NOT full-catalog completeness proof).
  NOT PRODUCTION_SUPPORTED.
- Missing: full large-catalog traversal; empty-board; registry portals for
  both bindings.
- Next: wave complete — next step recommended separately, not executed here.

### Ashby
- Implementation: `sources/ats/ashby.py` (name `ashby`).
- Catalog: GET `posting-api/job-board/{board}?includeCompensation=true`,
  single request; `descriptionHtml` preferred (code-read + JRCAD + W2 live
  comp probes: menlosecurity 200/17 jobs, snyk valid-empty).
- Identity: existing value preserved (NOT migrated to external id, W2.1).
- Catalog description: COMPLETE inline. Detail: none needed.
- Known tenants: 1 (horizon3ai). Live validated: 0 adapter scans.
- Empty endpoint-level evidence: yes (snyk probe). Status: EXPERIMENTAL.
- Missing: adapter scans; multi-tenant blocked (1 portal in registry).
- Next: single adapter scan when cheap.

### SuccessFactors (RMK authoritative; RSS deferred)
- Implementation: `sources/ats/successfactors.py` (name `successfactors_rmk`).
- Catalog: RMK HTML startrow pages, no catalog description (code-read + JRCAD
  incl. page-budget test). RSS feed NOT adopted (parity PARITY_UNRESOLVED,
  KPMG RMK walk exceeded 12-wire ceiling → STOP, W2.1).
- Identity: RMK-result adapter-native. Detail: none (RMK rows flow to
  official_html path if eligible — unproven live).
- Known tenants: ~54 RMK-style portals (largest registry footprint).
- Live validated: 0 completed (RMK walk never finished within budget).
- Status: EXPERIMENTAL. Missing: one bounded RMK completion on a SMALL tenant.
- Next: small-tenant RMK validation before any RSS revisit. RSS parity stays
  a separate task.

### Teamtailor
- Implementation: `sources/ats/teamtailor.py` (name `teamtailor`).
- Catalog: GET `{tenant}.teamtailor.com/jobs.json`, single request, no
  pagination (W11 live: polestar 27 items JSON_SUPERIOR over RSS).
- Identity: numeric URL id. Catalog description: COMPLETE inline (content_html).
- Detail: none needed. Known tenants: 1. Live validated: 1 (W11 probe +
  15 fixture tests on saved bodies).
- Empty: shape-guard covered offline (`items: []` valid empty).
- Status: VALIDATED_ONE_TENANT. Missing: JRC-adapter live scan (probe used
  evidence fetch); multi-tenant blocked (1 portal).
- Next: none without source creation.

### Workable
- Implementation: `sources/ats/workable.py` (name `workable`).
- Catalog: GET widget `accounts/{slug}?details=true`, single request,
  INLINE_DETAIL_CONFIRMED (W11 live: starling-bank 104 rows/49 shortcodes,
  104/104 descriptions; replaces 1+49 detail fetches).
- Identity: shortcode, multi-location rows combined. Empty ambiguous
  (200+empty completes false with warning — documented, tested).
- Detail: none needed. Known tenants: 0 in registry. Live validated: 1
  (W11 probe + fixture tests).
- Status: VALIDATED_ONE_TENANT. Missing: registry presence; multi-tenant n/a.
- Next: none (no portal to scan).

## Tier 3

### Mercedes / Beesite (declarative)
- Implementation: spec `specs/mercedes.json` (Beesite), exact binding
  `https://jobs.mercedes-benz.com`. Catalog offset-only; full
  Tasks/Qualifications declarative; 2798-total/57-req offline study.
- Live validated: 0 (frozen v0.1, no live declarative scan yet).
- Status: EXPERIMENTAL. Missing: live catalog + detail-free completeness proof.
- Next: after Eightfold.

### BambooHR
- Implementation: NONE (reference only: `embed2.php` catalog +
  `/careers/{id}/detail`; ats-jobs `/careers/list` STALE-404; EXT fan-out
  rejected). Live tenants observed returned valid-but-empty (`blankState`).
- Status: EXPERIMENTAL (protocol known, no adapter, no non-empty live).
- Missing: one observed non-empty listing before ANY integration.
- Next: none — no brute-force; stays unintegrated until evidence appears.

## Later / special cases (protocol-specific, no live validation this phase)

- Google Careers: EXPERIMENTAL (adapter `google_careers_rpc` + tests exist;
  anonymous BOQ RPC understood; live behavior unverified, CODE_PRESENT).
- Apple: NEEDS_EXTENSION (JSON-vs-form catalog scope unresolved).
- Meta: NEEDS_EXTENSION (Comet doc_id stale, UNRESOLVED).
- Amazon: NEEDS_EXTENSION (PASS_V01 reclassified on review).
- Cloudflare: NEEDS_EXTENSION (single-chunk only, pagination unproven;
  archived PASS_V01_then_revoked).

## Coverage note (registry scan-enabled counts)

RMK/SF ~54, Workday 17 adapter-served (supports() contract; branded
frontends excluded), Greenhouse 12 exact-family (+2 embedded, +1 gh_jid
signal — neither served by GreenhouseAdapter, which requires family
"Greenhouse" on a direct host), Oracle RC 4, Lever 2,
SR 1, Ashby 1, Teamtailor 1, BambooHR 0, Workable 0. Tier order kept
(Tier-1 = mature runtime × multi-tenant feasibility), not raw counts:
SF's footprint is HTML-scrape fragile and waits for a small-tenant proof.
