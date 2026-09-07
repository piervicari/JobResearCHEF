# Decision 0061: External ATS protocol/parser improvements from Wave 2 are selectively adopted with JobResearCHEF ownership

- Status: ACCEPTED
- Date: 2026-09-07

## Decision

Adopt the Wave 2 shortlist as adapter-level changes only. JobResearCHEF
retains network, identity, completeness, and lifecycle ownership; external
repos stay protocol/parser reference (no dependency, no runtime reuse).

- SuccessFactors: NOT implemented. Parity validation on `careers.kpmg.it`
  returned PARITY_UNRESOLVED (RSS: 202 items / 4.2 MB confirmed; the RMK
  production-adapter walk needed >11 requests, past the 12-wire ceiling →
  STOP per rule). The feed stays reference evidence; RMK HTML remains the
  only authoritative path. No feed adapter, no fallback engine built.
- Oracle: requested `limit` 25 → 200 (proven live: total 1361, 200 rows)
  with NEW total-driven adaptive pagination (offset advances by actual
  received count; termination by `TotalJobsCount` only — safe under silent
  server caps). Parser: employment chain WorkerType→JobType→ContractType→
  JobSchedule (raw strings), `WorkplaceTypeCode`-first workplace,
  `CreatedOn` fallback. RequisitionNumber variants NOT adopted.
- Lever: description assembled from HTML `description` + `lists[]` sections
  (exact-normalized dedup, `descriptionPlain` fallback), `createdAt`
  epoch-ms → posted_at. Contract: `RawJob.description` may hold HTML —
  downstream `normalize_job`/`html_to_text` strips it (verified in
  `pipeline/normalizer.py`).
- Workday: `timeType` → employment_type, `remoteType` → workplace_type
  (raw strings, no enum mapping). Protocol/bootstrap/pagination untouched.
- SmartRecruiters: `typeOfEmployment.id`-first employment (raw string).
  `refNumber` NOT promoted to requisition_id.
- Greenhouse: single-unescape of double-encoded `content`, placeholder
  requisition filter (See Opening ID/TBD/N/A/TBA). Guards and `id`
  identity untouched.
- Ashby: `?includeCompensation=true` on the single request (proven accepted
  live), `descriptionHtml` preferred (proven richer live).

## Identity rule (binding)

`requisition_id` feeds the variant identity digest
(`pipeline/source_identity.py`), and Oracle/SmartRecruiters requisition
changes would re-key existing rows. Therefore: Oracle keeps
`requisition_id = Id`; SmartRecruiters keeps `None`; Ashby keeps
`jobUrl` identity (external bare `id` rejected); all other
`source_job_id`/URL semantics unchanged. Department/team/salary metadata
without house fields rides in the already-full `raw_payload` (no mutation,
no migration) — Teamtailor precedent.

## What was NOT done

No N+1 in any catalog scan. No external afetch/fan-out/browser/proxy.
No Workday 2K facet subdivision (NEEDS_DESIGN). No Eightfold, BambooHR,
SourceSpec, DB, or migration changes. Phase 3 detail protocols recorded
only: Workday CXS detail, SmartRecruiters `jobAd.sections`, Oracle ById,
Eightfold `position_details`.

## Provenance

- ats-scrapers @ `6b44a1badc9bfbf5cf176f75265cc5729e520e99`, MIT.
- ats-jobs @ `9edd4a6cb12fcf43d35e050d064edb61900b2683`, MIT.
- No verbatim code copied; endpoint shapes and mapping facts attributed
  here and in adapter module comments. Live evidence: Wave 2 (5 wire) +
  Wave 2.1 parity (12 wire, all sequential, 0 × 403/429/challenge).

## Consequences

- 17 new offline tests (`tests/test_wave2_1_reuse.py`); 1 existing Ashby
  URL assertion updated for the intended flag. Suite: 380 PASS / 0 FAIL.
- Request impact: Oracle up to 8× fewer catalog requests; SF unchanged
  (RMK cost stands); all others identical request counts, richer fields.

## Addendum (2026-09-07): Oracle total-count instability hardening

`TotalJobsCount` changing mid-scan now forces `is_complete_snapshot=false`
(always — a changed catalog cannot prove an atomic snapshot), while the
maximum total observed stays the reconciliation target: increases extend
the walk instead of truncating it, decreases cannot skip records
(empty-before-effective-total still fails safe; page/job caps bound the
walk). Correctness hardening of this decision, not a new decision.
