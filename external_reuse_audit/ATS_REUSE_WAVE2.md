# ATS Reuse Wave 2 — supported-adapter benchmark (AUDIT, no production changes)

Baseline: 363 PASS / 0 FAIL (rerun at Wave start). Production tree clean.
Frozen checkouts: ats-scrapers @ `6b44a1b` (2026-09-02, MIT), ats-jobs @
`9edd4a6` (2026-08-26, MIT). No re-clone. Reproducible on these commits.

Offline evidence: JRC 363 PASS (`test_ats_adapters.py`, greenhouse bulk,
declarative, teamtailor/workable) · ats-scrapers 151 PASS
(`test_ashby/eightfold/greenhouse/lever/successfactors/workday_guards`,
`PYTHONPATH=src`, extest venv) · ats-jobs 25 PASS (`node --test
test/providers.test.js`). No unit tests upstream for smartrecruiters/oracle.

Live probes (this Wave): 5 wire TOTAL, sequential, retries 0, concurrency 1,
browser/proxy/UA-rotation 0 — 403: 0, 429: 0, challenge: 0, all 2xx.
Raw bodies + status in `wave2_probes/`. JRC HttpFetcher only (no external
network engine, no `fetchCompany` fan-out).

| # | probe | result |
|---|-------|--------|
| 1 | `careers.kpmg.it/sitemal.xml` (HIGH ×2, KPMG SF canary precedent) | 200, 4.2 MB RSS, ~200+ items, 25 KB inline descriptions → RSS CONFIRMED |
| 2 | Honeywell Oracle REST `limit=200` (HIGH ×2, exact URL+site CX_1) | 200, total 1361, 200 rows returned → limit=200 HONORED |
| 3 | `api.lever.co/v0/postings/sophos?mode=json&skip=0&limit=1` (HIGH ×2) | 200, exactly 1 item → skip/limit HONORED, JRC pagination valid |
| 4 | Ashby `snyk?includeCompensation=true` (HIGH) | 200, valid shape, `jobs:[]` → flag accepted, content unverifiable on empty board |
| 5 | Ashby `menlosecurity?includeCompensation=true` (HIGH) | 200, 17 jobs, `compensation{}` structure + `descriptionHtml` 7329 vs `descriptionPlain` 5500 chars → flag + HTML preference CONFIRMED |

RawJob has no salary/department/team/is_remote fields (employment_type and
workplace_type strings only) — compensation/department reuse lands in
`raw_payload`, same precedent as the Teamtailor decision. This bounds all
parser adaptations below to house-shaped string fields + raw enrichment.

## Per-ATS decisions

### Workday — KEEP_JRC + parser + detail strategy (ats-jobs confirms)
Same endpoint everywhere (`POST …/wday/cxs/{tenant}/{site}/jobs`, limit 20 =
hard cap, `total` pagination). JRC landing-bootstrap (tenant+siteId regex) is
more robust than the external URL-pattern split (which needs the `wdN`
instance in the URL). External-only value, all parser-level: `timeType` →
employment enum (JRC captures NOTHING here), `jobFamilyGroup` → department
(raw), `remoteType` mapping, `postedOn` relative label, location-rollup
resolution. Detail protocol `GET {cxs}{externalPath}` → `jobPostingInfo`
(description/startDate/timeType/locations) confirmed by BOTH externals =
Phase 3 input, no N+1 in catalog. 2K-query cap + facet subdivision is real
(Accenture ~61K) but needs design (recursive fan-out) — JRC honestly caps at
100 pages/2000 with `complete=false`; NOT Wave 2.1. Request model identical:
1 bootstrap + ceil(N/20).

### SuccessFactors — ADOPT_EXTERNAL_PROTOCOL (HIGH IMPACT)
JRC scrapes RMK HTML pages (N requests, title+location only, NO description,
fragile selectors). External uses credential-free XML feeds: RM sites expose
`/sitemal.xml` (RSS: link, 25 KB inline description, ReqId-equivalent `g:id`,
`g:job_function`, `g:location`, `g:employer`, guid), legacy sites expose
`/career?...resultType=XML` (ReqId, template-rendered description,
department, posted date). Probe 1 CONFIRMED the feed live on a HIGH tenant.
Wave 2.1: new feed adapter (~150 LOC), keep RMK HTML as fallback for tenants
without a feed. Caveat for 2.1 design: feed size (~21 KB/job → 2500 jobs ≈
50 MB exceeds the 20 MB `max_response_bytes` default) — keep the HTML path
for huge tenants. ats-jobs: NOT_AVAILABLE.

### SmartRecruiters — KEEP_JRC + parser (MEDIUM)
Catalog protocol identical in all three (`limit=100&offset`, `totalFound`).
External-only value: `department.label` (+`function.label` fallback),
`refNumber` → requisition_id (JRC captures NONE — real gap),
`typeOfEmployment.id` enum mapping (JRC uses the localized label only),
explicit remote False. Detail protocol `/postings/{id}` → `jobAd.sections`
(jobDescription + qualifications + additionalInformation + companyDescription)
= Phase 3 input. No page-size or N+1 change.

### Greenhouse — KEEP_JRC + parser (small MEDIUM)
Identical protocol (`?content=true`, single request, full catalog + full
description — the ideal already). JRC guards strictly; external does
`payload.get("jobs", [])` + `item["absolute_url"]` (weaker). Adopt:
departments/offices/metadata/internal_job_id into raw, HTML-unescape
(double-encoded `content`), requisition placeholder filter ("See Opening
ID"/"TBD"/"N/A" — JRC keeps verbatim). ats-jobs confirms endpoint +
`emptyMeansExists:true`, consistent with JRC valid-empty semantics.

### Eightfold — KEEP_JRC (declarative) + detail strategy
External (ats-scrapers, 683 lines) confirms the PCSX family: same search
shape, server-fixed page size 10, `data.count` total, `position_details`
per-job detail protocol (= Phase 3 input), SmartApply variant endpoint,
WAF/browser-fallback notes (runtime REJECT — reference only). No declarative
change in this Wave. ats-jobs: NOT_AVAILABLE → documented, not a gap.

### Lever — KEEP_JRC + parser (HIGH-value parser, same requests)
Probe 3 PROVED `skip/limit` honored → JRC pagination valid, no duplicate bug.
External single-fetch assumes all-at-once; JRC paging is safer for large
boards. Real gap is parser-only: external assembles description from HTML
`description` + `lists[]` sections (documents `descriptionPlain` drops
50–80% of body — JRC uses `descriptionPlain` only), plus `createdAt` →
posted_at (JRC: NONE), department/team (raw), salaryRange (raw), `country`/
`tags`/`additionalPlain` (raw). Note (no change): ats-jobs
`emptyMeansExists:false` — Lever 200+[] proves nothing; JRC empty→valid
snapshot with warning is accepted, risk low (site-keyed boards).

### Ashby — KEEP_JRC + flag + parser (MEDIUM)
Identical single-request protocol; external adds `?includeCompensation=true`
(probes 4–5: accepted, structure confirmed, tiers employer-dependent).
Adopt: flag (zero-risk) + `descriptionHtml` preference (7329 vs 5500 proven)
+ employment-enum map + isRemote/workplaceType logic + department/team/
secondaryLocations/address into raw. Compensation tiers → raw only (no house
field). JRC guards strictly; external indexes `item["title"]` directly.

### Oracle Recruiting Cloud — ADOPT page size + parser (HIGH + MEDIUM)
Same REST family (`finder=findReqs;siteNumber,limit,offset` — params MUST be
inside finder, both agree). Probe 2 PROVED `limit=200` honored (1361 total,
200 rows) vs JRC 25 → 8× fewer catalog requests, trivial change. Keep JRC's
`expand=requisitionList.secondaryLocations` (richer than external's plain
expand). Parser gaps: employment chain (WorkerType→JobType→ContractType→
JobSchedule), `WorkplaceTypeCode` enum, department chain
(Department→Organization→BusinessUnit), JobFamily team, RequisitionNumber
variants, ExternalURL, CreatedOn fallback. Detail protocol `…Details?finder=
ById;Id=` → ExternalDescription/Responsibilities/Qualifications = Phase 3
input. External header marks itself EXPERIMENTAL (envelope varies) — JRC
strict guards stay. ats-jobs: NOT_AVAILABLE.

## Request cost model (catalog wire requests)

| ATS | Impl | 50 jobs | 500 | 2500 | N+1 |
|-----|------|------:|----:|-----:|:----|
| Workday | JRC = ext | 1+3 | 1+25 | cap 2000 honest / facets design | detail selective (Phase 3) |
| SuccessFactors | JRC HTML | ~3 | ~21 | ~101 | none (no desc!) |
| SuccessFactors | ext RSS | 1 | 1 | 1–2 (size caveat) | none (inline) |
| SmartRecruiters | JRC = ext | 1 | 5 | 25 | detail selective (Phase 3) |
| Greenhouse | JRC = ext | 1 | 1 | 1 | none |
| Lever | JRC paged / ext single | 1 | 5 / 1 | 25 / 1 | none |
| Ashby | JRC = ext+flag | 1 | 1 | 1 | none |
| Oracle | JRC (25) | 1+2 | 1+20 | 1+100 | detail selective (Phase 3) |
| Oracle | ext (200) | 1+1 | 1+3 | 1+13 | detail selective (Phase 3) |
| Eightfold decl. | JRC = ext search | 5 | 50 | 250 | detail selective (Phase 3) |

## N+1 opportunities (Workable-class: catalog N+detail → 1)
NONE new. All single-request catalogs already carry full descriptions
(Greenhouse/Lever/Ashby/Workable/Teamtailor). Workday/SmartRecruiters/Oracle/
Eightfold/SuccessFactors-legacy details stay SELECTIVE (Phase 3), catalogs
stay cheap. SuccessFactors-RSS is the inverse win: fewer requests AND
descriptions appear.

## Wave 2.1 shortlist (impact-ordered, none implemented here)

HIGH:
1. SF feed adapter (new, ~150 LOC, ~8 tests, keep RMK fallback; handle
   20 MB ceiling for huge feeds) — fewer requests + descriptions.
2. Oracle `page_size` 25 → 200 (~5 LOC + test) — 8× fewer requests.
3. Lever description assembly (`description`+`lists[]`) + `createdAt`→posted_at
   (~30 LOC + tests) — +50–80% body, same request count.
MEDIUM:
4. Workday `timeType`→employment_type + `remoteType`→workplace_type + raw
   facets (~30 LOC).
5. SmartRecruiters `refNumber`→requisition_id + employment-by-id + dept/raw (~25 LOC).
6. Greenhouse raw (dept/offices/metadata/internal_job_id) + unescape + req filter (~25 LOC).
7. Ashby comp flag + `descriptionHtml` + employment map + raw (~25 LOC).
8. Phase-3 detail inputs: Workday cxs detail, SR `jobAd.sections`, Oracle ById,
   Eightfold `position_details`. (Phase 3 still paused.)
NO CHANGE: SR/Greenhouse/Ashby/Lever-paging/Workday-bootstrap/Eightfold protocols;
Workday 2K subdivision (NEEDS_DESIGN, not 2.1); BambooHR (still
READY_PENDING_VALIDATION, untouched); Teamtailor/Workable (Wave 1.1, not re-compared).

## External reuse accounting
JRC best/equivalent protocol: 7 of 8 (all but SF). External protocol better: 1
(SF RSS). Parser/details-only reuse: 7 (Workday, SR, Greenhouse, Lever, Ashby,
Oracle, Eightfold-detail). No external comparator: SF/ Eightfold/ Oracle have
no ats-jobs provider (NOT_AVAILABLE — documented, not gaps); every Wave-2 ATS
has an ats-scrapers comparator.

## Live safety (this Wave)
New wire: 5 (4 tenants + 1 follow-up). 2xx: 5. 403/429/challenge: 0.
Retries: 0. Concurrency: 1. Browser/proxy/UA-rotation: 0. No cookies/secrets
stored (bodies are public job data; status JSON has URLs only).

## Production impact
`src/`: 0. `tests/`: 0. DB: 0. SourceSpec: 0. `external_reuse_audit/`: docs +
`wave2_probe.py` + `wave2_probes/` only. One critical production bug found:
NONE (Lever dup-risk hypothesis disproven by probe 3).

VERDICT: `READY_FOR_REUSE_WAVE2_1`
