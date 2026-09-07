# Decision 0062: Detail hydration is a bounded selective second stage, never part of authoritative catalog enumeration

- Status: ACCEPTED
- Date: 2026-09-07

## Decision

Extend the existing detail pipeline (`pipeline/detail_enrichment.py`,
`research_agent enrich-details`) with structured ATS detail for four
providers; catalog scans stay detail-free.

- Triage before detail: only `active` rows with `ai_status` in
  (`CYBER`, `NEEDS_MORE_DETAIL`) and effectively incomplete descriptions
  (`< min_description_chars`, default 500) are candidates. `NON_CYBER`,
  closed, already-complete, and inline-complete adapters (workable,
  teamtailor, greenhouse, lever, ashby, ...) are never selected.
- Existing HttpFetcher with existing budgets/pacing/abort semantics; one
  request per job, sequential, `limit` + `max_jobs_per_host` caps.
  `HostCircuitOpenError` / `AccessChallengeError` /
  `RequestBudgetExceededError` stop the run (no host hammering).
- Provider detail protocols (Wave 2 external evidence, no external
  runtime): Workday `GET {origin}/wday/cxs/{tenant}/{site}{externalPath}`
  (ats-scrapers workday.py); SmartRecruiters
  `GET api.smartrecruiters.com/v1/companies/{slug}/postings/{id}` →
  `jobAd.sections` in fixed order jobDescription/qualifications/
  additionalInformation/companyDescription; Oracle
  `...Details?finder=ById;Id=` → ExternalDescription/Responsibilities/
  Qualifications; Eightfold `position_details` rendered AND parsed purely
  through the frozen SourceSpec detail block (`render_detail_request` +
  `merge_detail_into_job`, `data`-unwrapped).
- Semantic hash (`_store_detail`, unchanged) drives AI requeue: first
  hydration → `PENDING_AI` + clear `ai_last_error`; identical detail →
  no requeue; description- or qualifications-only change → requeue.
  Empty detail responses are failures: no store, no complete flag, no
  requeue (fail closed).
- Identity preserved: no `source_job_id`/URL/`requisition_id` changes;
  unrenderable rows are skipped, never guessed; same-host rule kept with
  one sanctioned exception (SmartRecruiters first-party API host).
- No DB migration (all `detail_*` fields pre-existed), no new service/
  queue/scheduler/client, no SourceSpec change, no catalog change.

## Cost model (synthetic, per provider)

catalog 2,000 jobs → triage relevant 35 → already complete 10 →
detail candidates 25 → detail requests ≤25 (+≤2 robots only for the HTML
path; structured APIs skip robots) → AI requeues ≤25. Detail requests
scale with RELEVANT INCOMPLETE JOBS, never catalog size; `limit=5`
cannot fetch more than 5 (+robots).

## Provenance

- ats-scrapers @ `6b44a1badc9bfbf5cf176f75265cc5729e520e99`, MIT.
- ats-jobs @ `9edd4a6cb12fcf43d35e050d064edb61900b2683`, MIT.
- No verbatim copy; URL shapes + section orders attributed here and in
  module comments. Zero new live wire in Phase 3 (all endpoints already
  proven in Wave 2).

## Consequences

- 15 new offline tests (`tests/test_phase3_detail.py`); 1 intended
  assertion update (workday candidate now renders CXS, not `/apply`).
  Suite: 398 PASS / 0 FAIL.
- Workday HTML `/apply` detail superseded by CXS JSON for workday rows
  (the `/apply` JSON-LD unit tests for the shared helper stay green).

## Addendum (2026-09-07): Microsoft declarative detail fix (Phase 3.1)

- Sanctioned cross-host: a declarative detail host differing from the
  portal host is allowed ONLY when it is the bound SourceSpec's own
  explicit detail URL (Microsoft portal `careers.microsoft.com` →
  `microsoft.eightfold.ai`), AND the row's source company equals the
  company the operator bound to that exact portal URL (`bindings.json`).
  Anything else (redirects, payload URLs, heuristics, mismatched rows)
  is rejected before HTTP. No generic allowlist.
- Request fidelity: declarative detail executes the full
  SourceSpec-rendered request through the existing Phase-1 bridge
  (`to_fetch_request`) — method, URL, headers (incl. `Accept-Language`),
  query (`position_id`/`domain`/`hl` exactly once), body. No second
  bridge, no reconstruction.
- Path semantics: extraction paths evaluate on the FULL response root as
  declared. NVIDIA `detail.description_path` corrected to
  `"data.jobDescription"` (one string): the wrapped `{data: {...}}`
  envelope is proven by external Eightfold code, the Microsoft spec for
  the same endpoint family, and the saved detail fixture — the NVIDIA
  value was the inconsistent one. `merge_detail_into_job` has no other
  consumer. No schema change.
