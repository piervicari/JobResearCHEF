# ATS validation — Workday — 2026-09-08

## Baseline

- HEAD `d550904`, clean tree, `git diff --check` clean.
- Full suite before: 412 passed / 0 failed (`PYTHONPATH=src .venv/bin/python -m pytest tests/ -q`).
- Production DB `data/research_agent.db`: 82227200 bytes / mtime 1788364672;
  536 portals / 492 scan-enabled / 29 runs / 5789 jobs (read-only opens only).

## Implementation (code-read)

- Adapter `src/research_agent/sources/ats/workday.py`, name `workday`,
  `page_size = 20` (verified live: `limit=20`, offsets 0, 20, 40, …), `max_pages = 100`.
- Routing: direct host (`*.myworkdayjobs.com` / `*.myworkdaysite.com`) + family
  `workday`/`workday recruiting`. No hardcoded tenant/siteId.
- Bootstrap: landing GET → regex `tenant:` / `siteId:` from HTML →
  `POST {origin}/wday/cxs/{tenant}/{site}/jobs`
  `{appliedFacets:{}, limit:20, offset:N, searchText:""}` until `total`-guarded
  natural end (`offset+len>=total` or short page); total-change warning;
  job-cap and page-cap guards mark snapshots incomplete.
- Identity: `bulletFields[0]` (requisition) else `externalPath` →
  `source_job_id` + `ats_job_id`; `source_url = {origin}/{site}{externalPath}`.
- Catalog payload keys observed live: `title, externalPath, bulletFields,
  locationsText, postedOn` — no `timeType`/`remoteType`, no inline description.
- Detail: `GET {origin}/wday/cxs/{tenant}/{site}{externalPath}` rendered from the
  stored row (`_render_workday_detail`), parsed by `_parse_workday_detail`
  (`jobPostingInfo.jobDescription`, `location`, `timeType`, `remoteType`);
  selective via `enrich-details`, never N+1.
- Persistence: `persist_scan_discoveries` after `assess_scan_gate`
  (same canonical path as `scan-discover`/`scan-pilot`).

## Registry (programmatic, routing contract)

- Adapter-served scan-enabled Workday portals: exactly 17 (expected 17, measured 17).
  Every one routes to `WorkdayAdapter` via the default registry (no generic fallback).
- Non-served lookalikes correctly excluded: `careers.qbe.com`, `careers.roche.com`,
  `www.gilead.com` (non-Workday hosts).

## Tenant selection (local evidence only, no discovery probing)

- 511 Brunello Cucinelli (`brunellocucinelli.wd3.myworkdayjobs.com/Cucinelli`, HEALTHY).
- 265 Proofpoint (`proofpoint.wd5.myworkdayjobs.com/proofpointcareers`, HEALTHY, cyber vendor).
- 5 Airbus (`ag.wd3.myworkdayjobs.com/Airbus`, HEALTHY, large board → pagination exercise).
- Rationale: all HEALTHY direct portals; size spread (small → very large);
  no prior live Workday evidence existed (only fixtures + W2 protocol agreement).

## Validation config (validation-only; production defaults 500/30 untouched)

- `max_jobs_per_portal = 500`, `max_pages_per_portal = 5` (catalog budget:
  1 bootstrap + ≤5 CXS pages per tenant), concurrency 1, retries 0,
  5 s per-domain pacing, 10 s between tenants, per-run wire cap 7.
- Zero-network preflight: `supports()` true for all 3; registry `select()` →
  `WorkdayAdapter`; tenant/siteId derived at runtime from landing HTML.

## Tenant 1 — Brunello Cucinelli (portal 511) — COMPLETE

- Bootstrap: GET landing → 200 → tenant `brunellocucinelli`, site `Cucinelli`.
- Catalog endpoint: `POST .../wday/cxs/brunellocucinelli/Cucinelli/jobs`.
- Pages (method/path/status): 1 GET 200 + 3 POST 200; offsets `[0, 20, 40]`,
  items `[20, 20, 4]`, totals seen `[44, 0, 0]`; natural end (short page), no repeat,
  no skip, no post-terminal request.
- API rows 44 = adapter rows 44 = unique IDs 44 = persisted 44;
  `complete_snapshot` TRUE; duplicates 0, malformed/skipped 0, missing 0, unexpected 0.
- Live wires: 4. Retries 0.

## Tenant 2 — Proofpoint (portal 265) — INCOMPLETE (page budget, clean stop)

- Bootstrap: tenant `proofpoint`, site `proofpointcareers`.
- 1 GET 200 + 5 POST 200; offsets `[0, 20, 40, 60, 80]`, 20 items each,
  totals seen `[143, 0, 0, 0, 0]`; stopped at the 5-page safety cap (43 rows beyond
  budget, not fetched per rule — no budget increase).
- Observed pages exact: API 100 = adapter 100 = unique 100 = persisted 100;
  `complete_snapshot` FALSE; duplicates 0, malformed 0, missing/unexpected 0.
- Live wires: 6. Retries 0.

## Tenant 3 — Airbus (portal 5) — INCOMPLETE (page budget, clean stop)

- Bootstrap: tenant `ag`, site `Airbus`.
- 1 GET 200 + 5 POST 200; offsets `[0, 20, 40, 60, 80]`, 20 items each,
  totals seen `[2000, 0, 0, 0, 0]`; stopped at the 5-page safety cap.
- Observed pages exact: API 100 = adapter 100 = unique 100 = persisted 100;
  `complete_snapshot` FALSE; duplicates 0, malformed 0, missing/unexpected 0.
- Live wires: 6. Retries 0.

## Pagination

- Multi-page observed live on all 3 tenants (3, 5, 5 pages).
- Offset sequences exact, no repeats/skips/duplication, no post-terminal request.
- Systematic quirk: `total` is authoritative on page 1 only; pages 2+ report
  `total: 0` on all 3 tenants. The adapter warns (`total changed … -> 0`) and
  termination stays correct (short-page rule; page-cap rule). Recorded as a watch
  item, not a defect: no data loss, all flags correct (see Defects).

## Catalog content

- Title 244/244, requisition 244/244, location 243/244 (one Airbus row empty).
- Employment 0/244, workplace 0/244 (no `timeType`/`remoteType` in catalog rows —
  the W2.1 mapping is unexercised live on catalog; detail hydrates employment).
- Catalog description 0/244 (no inline descriptions; detail required — as designed).
- Identity: requisition-style native IDs (`JR…`/`R…`), 1 row per native ID,
  `source_url` = site + externalPath on all rows; no collisions.
- Sample: 511 `JR101204` TRAVEL OFFICE INTERN (Solomeo); 265 `R14702`
  Account Manager (Draper, UT); 5 `JR10403495` Rotor System Blade … (Paris Area).

## Detail (selective, existing path)

- Candidates (deterministic, lowest id per tenant, marked NEEDS_MORE_DETAIL in the
  disposable DB only — no LLM): job 1 (511), job 45 (265), job 145 (145→portal 5).
- Pre-network: existing renderer verified per row — correct CXS detail URLs
  (`/wday/cxs/{tenant}/{site}{externalPath}`), same-host, structured.
- Live: 3 requests, all 200, parser `workday_cxs_detail`:
  - 511 `JR100132`: desc 0 → 332; employment `''` → `Full time`.
  - 265 `R14702`: desc 0 → 4493; employment → `Full time`.
  - 5 `JR10403495`: desc 0 → 5960; employment → `Full time`.
- Identity invariant holds: `source_job_id`/`ats_job_id`/`requisition_id`
  unchanged on all 3 rows (detail never re-keys).
- Detail wires: 3 (1 per tenant; never N+1).

## Safety

- ATS wire attempts total: 21 (catalog 16 + detail 3 + 1 failed first attempt +
  1 transport diagnostic; replay/analysis 0 wires). Budget respected, no overrun.
- Retries 0, 403/429/challenges 0, unexpected-auth 0, unsafe-protocol drift 0.
- Concurrency 1 throughout; no browser/proxy/bypass; LLM calls 0
  (triage/analysis untouched; all rows PENDING_AI by construction).
- Production DB after: 82227200 bytes / mtime 1788364672;
  536 / 492 / 29 / 5789 — unchanged. Disposable DB only written.

## Defects

- Product defects found live: none. No implementation change, no tests added
  (per policy: no change without live-proven defect).
- Harness issues (validation tooling, not product — fixed during the wave):
  body-recording transport double-decoded gzip (fixed, unit-verified offline);
  initial driver omitted the canonical gate+persist step (fixed by replaying saved
  bodies through the real scan→gate→persist path at 0 extra wires, Lever-E1 precedent).
- Watch item (not a defect on observed evidence): when `total` flips to 0,
  the `offset+len>=total` clause is vacuous and termination rests on the short-page
  rule; a hypothetical empty non-terminal page with `total: 0` would read complete.
  Never observed (all short/empty pages were terminal and exact). Left as a
  production-support hardening note; no redesign without live proof.

## Status

- `EXPERIMENTAL → MULTI_TENANT_VALIDATED` (3 canonical tenants live 2026-09-08).
  NOT PRODUCTION_SUPPORTED. Remaining gates: live empty-board observation;
  full-traversal proof on 100+ boards (265/5 stopped at the 5-page budget);
  `total→0` hardening note above.
- Evidence: disposable DB `output/workday_wave_20260908/validation.db`;
  16 saved wire bodies `output/workday_wave_20260908/bodies/`;
  3 saved detail bodies `output/workday_wave_20260908/detail_cache/`;
  drivers `driver.py` / `replay.py` / `analyze.py` / `detail.py` (same dir).

## Follow-up replay note (0 wires)

- The live runs exercised scan→adapter→fetch; persistence ran via offline replay of
  the 16 saved bodies through the real `scan_portals` + gate + `persist_scan_discoveries`
  (MockTransport serving saved bytes): 44/44, 100/100, 100/100 persisted,
  gate passed all 3, `complete_snapshot` TRUE only for 511. No product defect
  (harness sequencing only) — no code changed.
