# ATS validation — Lever — 2026-09-08

## Baseline

- 412 passed / 0 failed, clean tree, `git diff --check` clean.

## Implementation

- Adapter `sources/ats/lever.py`, name `lever`, `page_size = 100`.
- Routing: host `jobs.lever.co` → `api.lever.co`,
  `jobs.eu.lever.co` → `api.eu.lever.co`; exact family `Lever`; slug = first
  portal path segment. No company branches (code-read).
- Catalog: `GET /v0/postings/{slug}?mode=json&skip=&limit=100` until a page
  returns < 100; job-cap and page-cap guards mark snapshots incomplete.
- Identity: posting `id` → `source_job_id` + `ats_job_id` (unchanged by
  enrichment work, W2.1). Description: `description` + `lists[]` assembly,
  `descriptionPlain` fallback only; `createdAt` → posted_at.
- Prior evidence: W2 live skiplimit probe (sophos, pagination shape);
  JRCAD fixture tests; no prior JRC adapter scan.

## Registry (programmatic, routing contract)

- Adapter-served scan-enabled Lever tenants: exactly 2, both HEALTHY:
  - 214 `https://jobs.lever.co/safe` → slug `safe`, API `api.lever.co`
  - 215 `https://jobs.lever.co/watchguard` → slug `watchguard`, API `api.lever.co`
- Third canonical tenant available: no (wave capped at these two).
- Zero-network preflight: `supports()` true both; slug/API deterministic;
  registry `select()` returns `LeverAdapter` for both (not generic HTML).

## Tenant 1 — safe (portal 214)

- Dry-run gate passed (Lever adapter, budgets shown).
- Live: 1 wire `GET /v0/postings/safe?mode=json&skip=0&limit=100` → 200,
  0 retries. Page items: 18 (< 100 → natural end, single page).
- API observed 18 = parser rows 18 = unique IDs 18; persisted 10
  (pilot `max_jobs_per_portal` cap — E1 distinction, not loss; offline
  reparse of the saved body at 0 extra wires proves 18/18).
  Duplicates 0, malformed/skipped 0, missing IDs 0, unexpected IDs 0.
- Content (offline): describable 18/18, createdAt 18/18,
  commitment 17/18, workplaceType 18/18, allLocations 18/18;
  parsed description min 5990 chars.
- Sample: `8543068c-35f2-4115-bff6-6b6372d65e5d`, Customer Success
  Advisor, Remote Americas, createdAt 1788755940564.

## Tenant 2 — watchguard (portal 215)

- Dry-run gate passed. Live: 1 wire `skip=0&limit=100` → 200, 0 retries.
  Page items: 24 (< 100 → natural end, single page).
- API 24 = parser 24 = unique 24; persisted 10 (same pilot cap).
  Duplicates 0, malformed 0, missing 0, unexpected 0.
- Content: describable 24/24, createdAt/commitment/workplaceType/
  allLocations 24/24; parsed desc min/med/max 1993/5222/39295, empty 0.
- Sample: `0e4b346a-3906-4b53-a4f8-ddd47acf8001`, Channel Account Manager,
  Madrid Spain, createdAt 1784705741329.

## Pagination

- Multi-page NOT observed live (both boards < 100 → single `skip=0` page
  each is the natural end). Skip sequence per tenant: `[0]`.
  No repeated/missing skip, no duplication, no post-terminal page.
  Pagination defect: none observable; multi-page code path remains
  unit-tested only.

## Content / N+1

- Inline descriptions usable on all rows (min 1993 chars across tenants).
- Detail requests: 0 (no enrich run; none needed).

## Empty board

- Naturally observed: no. Contract evidence: fail-closed rows
  (`AdapterSchemaError` on missing id/text/hostedUrl) + `jobs: []`
  handling inherited from the shared scan path; no speculative test added.

## Safety

- Total ATS wires: 2 (1 + 1). Retries 0. 403/429/challenge: none.
  Sequential tenants, concurrency 1, disposable pilot DB (fresh 0/0 start;
  end: 20 jobs PENDING_AI untouched, 2 runs, 0 analyses).
- Production DB: size 82227200 / mtime 2 Set 17:57 unchanged;
  29 runs / 5789 jobs / 0 analyses before and after (read-only opens).
- Browser/proxy/bypass: none. LLM calls: 0 (triage/analysis/AI-repair untouched).

## Defects

- Found: none. Fixed: none. Tests added: none (no defect to pin;
  existing Lever fixture + Wave-2.1 assembly tests already cover the
  exercised paths).

## Follow-up closure (E1 evidence gap closed, 0 wires)

LIVE RUN (pilot cap `max_jobs_per_portal = 10`):
safe 18 API / 10 adapter+persisted; watchguard 24 API / 10 adapter+persisted.
`complete_snapshot` was FALSE in the live runs purely from cap truncation
(lever.py: exceeding the cap truncates and clears the flag — confirmed in code).

FOLLOW-UP VALIDATION (offline replay, 0 ATS wires):
saved live bodies replayed through the real `scan_portals` path
(adapter selection, preflight, context, parsing, gate, persistence —
only network transport substituted via MockTransport;
`max_jobs_per_portal = 500` production default, unchanged):
safe 18 / 18 unique / 18 persisted, `complete_snapshot` TRUE;
watchguard 24 / 24 unique / 24 persisted, `complete_snapshot` TRUE.
Missing/unexpected/duplicates 0 both tenants. Runs DISCOVERY_PERSISTED.
No product defect (B: experiment misconfiguration only) — no code changed.

## Final status

`EXPERIMENTAL → MULTI_TENANT_VALIDATED`, with the explicit limitation
that multi-tenant evidence is capped at the two canonical registry tenants.
NOT PRODUCTION_SUPPORTED. Remaining gates: live empty-board observation;
live multi-page pagination episode.
