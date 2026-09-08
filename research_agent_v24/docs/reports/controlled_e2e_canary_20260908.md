# Controlled end-to-end canary — 2026-09-08 (immutable evidence)

## Selected source (offline, PART 11)

- Company: ZeroFOX (cybersecurity vendor → positive triage likely)
- portal_id: 100
- Adapter: SmartRecruiters (production adapter, structured detail capable)
- Jobs URL: https://careers.smartrecruiters.com/ZeroFOX
- Registry state: scan_enabled=1, active_in_registry=1, HEALTHY/AVAILABLE
- Evidence: master universe v1_12 (1 eligible SR row) + registry DB read-only query
- No portal added, no discovery, no external validation.

## Pre-canary code fix (PARTs 1–8, offline)

- Bug confirmed: triage leaves positive candidates at PENDING_AI
  (`ai/job_triage.py`), selector required CYBER/NEEDS_MORE_DETAIL →
  documented scan→triage→enrich→analyze flow was broken.
- Fix: PENDING_AI eligible only with a valid `triage:` JobAiAnalysis whose
  input hash equals the row's CURRENT triage hash (reused
  `triage_input_for_source_job` helper, no duplicate algorithm) and
  `triage_candidate_cyber=true`. Untriaged/negative/stale → 0 candidates.
  Historical CYBER/NEEDS_MORE_DETAIL unchanged. No new states/columns/migration.
- Tests: A (untriaged→0), B (current positive→1), C (negative→0),
  D (stale hash→0), E (complete description→0, stays PENDING_AI),
  + CYBER-no-record regression. All offline, fake fetcher only.

## Disposable DB (PART 12)

- `research-agent prepare-pilot-db --replace` →
  `data/pilot/research_agent_pilot.db`, integrity ok,
  source_jobs=0, canonical_jobs=0, scan_runs=0. Portal 100 present, enabled.

## LLM preflight (PART 13, zero external requests)

- `llm-preflight --route job_light_classification`: google present, openrouter
  present; chain minimax-m3:free → minimax-m2.7:free → gemini-3.5-flash-lite.
- `llm-preflight --route job_analysis`: same keys; chain minimax-m3:free →
  minimax-m2.7:free → gemini-3.6-flash. Free-only policy intact, no overrides.

## Dry-run gates (PART 14, all zero-network)

- `scan-pilot --portal-id 100 --dry-run`: host=careers.smartrecruiters.com,
  ats=SmartRecruiters, concurrency=1, requests<=3, pages<=1, retries=0, 10s pacing.
- `triage-pending --portal-id 100 --limit 10 --batch-size 10 --dry-run`:
  planned_requests=0 (empty DB, as expected).
- `enrich-details --portal-id 100 --limit 1 --max-jobs-per-host 1 --dry-run`:
  selected_jobs=0 — runtime proof of the fixed contract (no triage → no detail).
- `analyze-pending --portal-id 100 --limit 1 --batch-size 1 --dry-run`: queue
  empty, fallback chain displayed.

## Live career scan (PART 15, ONE attempt)

- Command: `scan-pilot --portal-id 100` on the disposable DB.
- Result: status=SUCCESS http=200 requests=1 retries=0 adapter=smartrecruiters
  discovery=EMPTY_COMPLETE; persisted new=0 updated=0 pending_ai=0.
- Wire: GET https://api.smartrecruiters.com/v1/companies/ZeroFOX/postings?limit=100&offset=0
- Offline cache proof (zero new wire): payload keys offset/limit/totalFound/content,
  totalFound=0, content=[] — genuinely empty board, valid SR schema, NO protocol drift.

## Post-scan DB (PART 18, offline)

- scan_runs: 1 (COMPLETED / DISCOVERY_PERSISTED); source_jobs: 0; analyses: 0.
- complete_snapshot: not asserted (bounded single-page pilot; no CLOSED conclusions).

## Semantic stages (PARTs 19–23)

- Not executed: zero jobs persisted → triage/detail/analyze have no input.
  No states manipulated to force candidates. No LLM requests spent.

## Budgets (PART 16)

- Catalog wire: 1 (target ≤3). Detail wire: 0 (target ≤1). Total: 1.
  Retries: 0. 403/429/challenges/auth walls: none. Browser/proxy/UA rotation: none.

## Integrity (PARTs 25–26)

- Production DB `data/research_agent.db`: mtime unchanged (2 Set 17:57),
  29 scan_runs / 5789 jobs before and after → ZERO production writes.
- Duplicates: 0 (no rows). Source identity: n/a (no rows). Catalog N+1: none.

## Verdict

`PARTIAL_DETAIL` — transport + parser validated live on the real SR API
(HTTP 200, correct envelope, EMPTY correctly handled, run persisted
COMPLETED); the semantic chain (triage→detail→analyze) could not be
exercised because the board is genuinely empty. This is a valid
end-of-attempt result, not a failure: per protocol, no second live scan
was attempted after wire. The triage→detail contract itself is proven by
6 new offline tests + the pre-triage enrich dry run selecting 0.

## Follow-up (not executed)

- One structured-detail-specific canary against a registry portal with a
  verified non-empty board (SR preferred for the api.smartrecruiters.com
  sanctioned-host path; Workday/Oracle only inside the same ≤3/≤1 budget).
