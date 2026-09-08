# Controlled end-to-end canary #2 — 2026-09-08 (immutable evidence)

## Selected source (offline, B1–B2)

- Company: Honeywell; portal_id: 158; ATS: Oracle Recruiting Cloud
- Jobs URL: https://ibqbjb.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1
- Registry: scan_enabled=1 (health UNKNOWN, accepted: Wave-2 live proof overrides)
- Prior non-empty evidence: Wave-2 `oracle_limit200` probe, same exact host +
  siteNumber CX_1 → HTTP 200, total 1361, 200 rows, limit=200 accepted.
- Why: exact Wave-2-proven tenant in-registry; Oracle catalog descriptions
  typically incomplete (detail-eligible); Oracle ById detail Phase-3 supported.
  No SR non-empty proof existed; Lever/Ashby are inline-complete; no portal created.

## Defect found and fixed (B19 trivial-blocker path)

- Dry run post-triage selected 0 despite a valid positive triage record.
- Root cause: scanner persists `adapter.name` = `oracle_recruiting_cloud`
  (sources/ats/oracle.py:27) but the detail pipeline keyed only `oracle`
  in `_DETAIL_ADAPTERS` / `_STRUCTURED_ADAPTERS` / `_STRUCTURED_RENDERERS` /
  `_STRUCTURED_PARSERS` → production Oracle rows could NEVER enter detail.
  (Workday/SmartRecruiters names match; only Oracle mismatched.)
- Fix (4 alias lines, no renames, no identity change): accept
  `oracle_recruiting_cloud` alongside `oracle` in all four maps.
- Regression test added: production-name Oracle row renders ById + selects
  with current positive triage. No adapter/registry/DB/HttpFetcher change.

## Disposable DB (B3)

- `prepare-pilot-db --replace` → pilot DB, integrity ok, 0 jobs / 0 runs
  before scan. Path distinct from production DB.

## LLM preflight (B4, zero external requests)

- Both routes credentialed (google + openrouter present), free-only chains intact.

## Dry runs (B5)

- `scan-pilot --portal-id 158 --dry-run`: 1 portal, concurrency=1, ≤3 req,
  1 page, retries=0, 10s pacing, adapter Oracle Recruiting Cloud.
- `enrich-details --dry-run` pre-triage: selected_jobs=0 (contract proof).

## Live catalog scan (B6, ONE attempt)

- `scan-pilot --portal-id 158`: SUCCESS, http=200, requests=2 (landing + API
  `findReqs;siteNumber=CX_1,limit=200,offset=0`), retries=0,
  adapter=oracle_recruiting_cloud, discovery=JOBS_FOUND.
- Persisted: new=10, updated=0, pending_ai=10. No stop signals.

## Post-scan (B7, offline)

- Run COMPLETED/DISCOVERY_PERSISTED; 10/10 active; 10 PENDING_AI.
- Titles include Security Technician, Lead AI Architect, Senior IT Analyst;
  raw descriptions 0–354 chars (all <500). complete_snapshot not asserted
  (bounded single-page pilot).

## Triage (B8, one batch, zero career HTTP)

- `triage-pending --limit 10 --batch-size 10`: 1 batch, 10 jobs,
  9 NON_CYBER, 1 candidate (Senior IT Analyst m/f/d), 0 failures.
- Telemetry: openrouter minimax-m3:free 404 (no longer free) →
  minimax-m2.7:free 404 → google/gemini-3.5-flash-lite success (1.65s).
  Free-only policy intact; fallbacks are configured behavior, not overrides.

## Positive evidence + dry run (B9)

- Job 1 PENDING_AI; triage record `triage:google/gemini-3.5-flash-lite`,
  prompt cyber-triage-v2, needs_more_detail=1, valid, hash matches current.
- `enrich-details --dry-run` (limit=1, max-jobs=1): exactly 1 genuine
  candidate → same-host ById URL for requisition 149413.

## Live detail (B10, 1 wire)

- `enrich-details` (limit=1, max-jobs=1): 1 request, HTTP 200,
  parser=oracle_byid_detail, 0 → 4273 chars, location Bucuresti Romania,
  updated=1, job requeued PENDING_AI on semantic change.
- Actual detail host: ibqbjb.fa.ocs.oraclecloud.com (same-host). No N+1.

## Full analysis (B11, zero career HTTP)

- `analyze-pending` (limit=1, batch=1, default route): 0 analyzed, job stays
  PENDING_AI. All 3 routes failed: openrouter minimax-m3/m2.7 404 (free
  slugs retired upstream) + google gemini-3.6-flash HTTP 503 (transient
  overload). No rescan, no provider hammering — recorded as-is.

## Lineage (B12, job 1, req 149413)

- Catalog: portal 158, adapter/source oracle_recruiting_cloud, native 149413,
  raw 0 chars, payload 233f0e53… (1 SourceJob row, no duplicate).
- Triage: analysis 1, candidate_cyber positive, input hash c7626bba…
  (hash-matching current at selection time).
- Detail: same host, 4273 chars, hash 3f1d394d…, fetched 2026-09-08,
  identity unchanged.
- Analysis: none persisted; ai_status PENDING_AI; ai_attempts=2.

## Budgets (B13)

- Career-site: catalog 2 + detail 1 = 3 wires (target ≤4). Retries 0.
  401/403/429/challenges: none. Browser/proxy/rotation: none.
- LLM: triage 1 batch (3 attempts, 1 success); analysis 1 batch
  (3 attempts, 0 success). Reported separately per protocol.

## Integrity (B14–B15)

- Production DB: mtime 2 Set 17:57 unchanged; 29 runs / 5789 jobs before
  and after → ZERO production writes. Only pilot DB changed.
- One attempt only: no rerun, no second tenant after first wire.

## Verdict (B16)

`PARTIAL_AI` — real chain scan→persist→triage→selective detail all
observed live within budget; full analysis blocked by provider-side
failures (retired free slugs + transient 503), job safely queued.
