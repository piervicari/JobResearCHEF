# ATS validation — Greenhouse — 2026-09-08

## Implementation

- Adapter `sources/ats/greenhouse.py`, name `greenhouse`, `bulk_catalog=True`.
- Endpoint: `GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true`
  (token = first path segment of portal URL), single request, no pagination.
- Identity: posting `id` → `source_job_id` + `ats_job_id`; title/location
  never identity; `requisition_id` kept with placeholder filtering
  (`see opening id`/`tbd`/`n/a`/`tba` → None). No identity migration.
- Content: title, `location.name`, description = `content` unescaped once
  (downstream `html_to_text` finishes), `posted_at` from `first_published`/
  `updated_at`, `absolute_url` as source/apply URL, full posting in raw payload.
- Row contract: missing id/title/absolute_url → `AdapterSchemaError`
  (fail-closed); `{"jobs": []}` → complete snapshot + "zero active jobs"
  warning (unit-pinned this wave; live empty still unobserved).
- Prior evidence: W2 identical-endpoint agreement (JRC/EXT), JRCAD incl. bulk
  test, fixture `greenhouse_jobs.json`.

## Tenants (3 independent, sequential, same adapter)

1. Apiiro — portal 160, token `apiiro`. 1 wire, HTTP 200.
   API jobs 7 = unique ids 7 = persisted 7; dups 0; malformed 0; empty
   content 0. Sample: 7683988003, AI Engineer, Tel Aviv-Yafo, 3812 chars.
2. Chainguard — portal 165, token `chainguard`. 1 wire, HTTP 200.
   API jobs 82 = unique 82 = persisted 82; dups 0; malformed 0; empty 0.
   (Bulk path: 82 persisted, no pilot-cap truncation observed.)
3. SecurityScorecard — portal 170, token `securityscorecard`. 1 wire, HTTP 200.
   API jobs 39 = unique 39 = persisted 39; dups 0; malformed 0; empty 0.
   Sample: 8165396, Business Development Representative, Remote (Portugal),
   9510 content chars, requisition_id `2036` (real id kept).

## Completeness

- Authoritative single-response verified: for each tenant, saved-response
  bodies parsed offline show API count == unique valid IDs == persisted
  rows (7/7/7, 82/82/82, 39/39/39), 0 malformed, 0 intentionally filtered,
  0 duplicates. 0 additional wires for the proof (existing HTTP cache).
- No pilot-cap confusion: persisted counts equal API counts (bulk provider
  path), so no E1 distinction was needed in practice.
- Descriptions inline-complete on all rows (per-portal min 2916 chars) →
  detail requests 0 across all scans (no enrich run; AI frozen, ADR 0063).

## Safety

- Total career wires: 3 (1/tenant). Retries 0. 403/429/challenges: none.
  Sequential, concurrency 1, fresh disposable pilot DB (0/0 start).
- Production DB: mtime 2 Set 17:57 unchanged; 29 runs / 5789 jobs before
  and after → zero production writes. 128 pilot rows all PENDING_AI
  untouched; 0 AI analyses; 0 LLM calls.

## Defects

- None found. No production code changed. One unit test added pinning the
  `{"jobs": []}` → complete-snapshot contract (missing-gate documentation,
  not a fix).

## Final status

`EXPERIMENTAL → MULTI_TENANT_VALIDATED` (3 tenants, full-response coverage
proven, identity/dedup/content/safety clean, no defects).
NOT PRODUCTION_SUPPORTED: the single missing gate is a live empty-board
observation (`{"jobs": []}` handled in code + unit test, never seen live).
No fourth request was issued to hunt one (explicit no-search rule).
