# ATS Reuse Wave 2.1 — implementation status (do NOT rewrite ATS_REUSE_WAVE2.md)

## Adopted (all from the Wave 2 shortlist)

- Oracle: requested limit 200 + total-driven adaptive pagination + parser
  (employment chain, WorkplaceTypeCode, CreatedOn). With one IMPORTANT
  correction vs the shortlist: NOT a bare `page_size 25→200` — safe adoption
  required adaptive actual-count offsets (no `received < limit` termination,
  empty-before-total raises, total-change warnings kept).
- Lever: description assembly (`description` + `lists[]`, deduped,
  plain fallback) + `createdAt` → posted_at.
- Workday: `timeType`/`remoteType` parser. SmartRecruiters: employment-id
  parser. Greenhouse: unescape + req placeholder filter. Ashby: comp flag +
  `descriptionHtml`.

## Rejected / deferred (deliberate, with reason)

- SuccessFactors feed: parity PARITY_UNRESOLVED (RSS 202 items confirmed;
  RMK walk exceeded the 12-wire ceiling → STOP). No feed adapter, no
  fallback engine. RMK HTML stays sole authoritative path. Evidence kept in
  `wave2_probes/sf_parity_*` for a future retry on a smaller tenant.
- Oracle/SmartRecruiters requisition_id changes: would re-key the variant
  identity digest (`pipeline/source_identity.py`) → identity migration, not
  parser reuse. Deferred explicitly.
- Department/team/salary first-class fields: no house fields exist;
  already preserved verbatim in full `raw_payload` (no mutation — payload
  hashes must not churn). No-op by design.
- Workday 2K facet subdivision: NEEDS_DESIGN (recursive fan-out), not 2.1.
- Phase 3 details, Eightfold, BambooHR, SourceSpec, DB: untouched per scope.

## Difference from shortlist

Only two: (1) Oracle required the adaptive-pagination correction above;
(2) SuccessFactors HIGH item converted to no-build on unresolved parity.
Everything else implemented as specified. No scope creep.

## Verification

17 new offline tests, 1 intended assertion update (Ashby flag URL).
Full suite: 380 PASS / 0 FAIL. New live wire in 2.1: 12 (parity only),
all sequential via JRC HttpFetcher, 0 × 403/429/challenge.
Identity matrix: all 5 parser ATS report identity NO-change (see FINAL REPORT).
