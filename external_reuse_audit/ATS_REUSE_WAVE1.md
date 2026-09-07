# ATS Reuse Wave 1 — BambooHR / Teamtailor / Workable (audit + test + decision, NO implementation)

> SUPERSEDED FOR IMPLEMENTATION CHOICE BY ATS_REUSE_WAVE1_1.md.
> This file is the historical Wave 1 record (audit + upstream tests + first
> probes, written before the Wave 1.1 protocol micro-probes). Current
> protocol decisions and integration status live in ATS_REUSE_WAVE1_1.md.

Upstream checkouts (frozen, NOT re-cloned for this task):
- ats-scrapers @ 6b44a1badc9bfbf5cf176f75265cc5729e520e99 (2026-09-02, MIT, Kalil Bouzigues)
- ats-jobs @ 9edd4a6cb12fcf43d35e050d064edb61900b2683 (2026-08-26, MIT)
- JobResearCHEF: detection-only for Teamtailor (comment + family label); no adapter for any of the three.

Safety screening: `ats-jobs.fetchCompany(domain)` = REJECT as runtime
(parallel 12-provider probing + slug variants + website discovery).
Explicit `provider:slug` single invocation = SAFE_TO_TEST_WITH_WRAPPER
(not used live here; probes used JobResearCHEF HttpFetcher directly).
ats-scrapers `afetch` runtimes = UNSAFE_RUNTIME_PATTERN (async fan-out 4-8,
proxy params, browser fallbacks elsewhere) — reused as SAFE_REFERENCE
protocol/parsing only. No external network stack was executed.

## BambooHR

Protocol (ats-scrapers, verified live shape): `GET https://{slug}.bamboohr.com/jobs/embed2.php`
static HTML widget grouped by department (`bhrDepartmentID_*` blocks,
`bhrPositionID_{id}` items, title link + `BambooHR-ATS-Location` span).
Old `/careers/list` JSON deprecated 2024 → 404 (docstring; ats-jobs still
points at it = STALE reference). No pagination (single widget). Detail:
`GET /careers/{id}/detail` JSON (`result.jobOpening`: description HTML,
employmentStatusLabel, compensation, datePosted, location{city,state,
addressCountry}, locationType) — N+1, best-effort upstream. No auth/cookies/
browser. Stable ID = numeric position id. Location terse in listing,
canonical in detail. Posted date only in detail. Qualifications: not
separate (inside description HTML).
Offline: upstream fixture tests 58 passed (incl. bamboohr widget variants).
Live probe: `hp` → 200 empty (0 bytes, no board); `detectify` → 200 valid
tenant, zero open positions (blankState), parser correctly returns [].
Request count: 2. Semantic coverage live: endpoint+tenant OK, job rows
NOT observed live (empty boards), parsing proven offline only.
Decision: REUSE_WITH_SMALL_ADAPTER (HTML catalog needs procedural parsing
outside v0.1 JSON extraction; detail fits existing enrichment path).

## Teamtailor

Protocol (ats-scrapers, VERIFIED LIVE): `GET https://{slug}.teamtailor.com/jobs.rss`
single-request full catalog (polestar: 199,852 bytes, 27 jobs). Per item:
title, link (`/jobs/{numeric_id}-*` stable ID), pubDate, guid fallback,
`tt:` location/department/role, HTML description inline (5-6k chars observed),
remoteStatus. Shape guards: root must be `<rss>` (else ScraperError, never
silent-empty); per-item dedup by id. No auth/cookies/browser/pagination.
Alternate (ats-jobs, reference only): `/jobs.json` (`items[]` with
`content_html` + schema.org `_jobposting`) — NOT probed live (budget).
Offline: upstream tests passed; ats-jobs node suite 25 passed incl. parsing.
Live probe: `canva` → 404 (no board, slug collision — HIGH row disproven);
`polestar` → 200, 27/27 jobs parsed with title/location/url/desc/dept.
Request count: 2. Decision: REUSE_WITH_SMALL_ADAPTER (verified shape is XML;
stdlib ET parse ≈30 lines; `/jobs.json` noted as future simplification
toward v0.1 if verified).

## Workable

Protocol (both repos agree, VERIFIED LIVE): `GET
https://apply.workable.com/api/v1/widget/accounts/{slug}` single JSON
(`name`, `jobs[]`, no pagination). Rate-limit warning upstream
(concurrency>2 → 429s; we ran sequential, zero 429). Fields: shortcode
(stable ID; multi-location rows repeat it — upstream combines with ` | `),
title, url/application_url, city/state/country + `locations[]`,
department/function, `type` (freeform → enum map), telecommuting bool,
published_on/created_at. NO description in widget (verified: keys lack it).
Detail: `GET /{slug}/jobs/view/{shortcode}.md` Markdown (description +
requirements + benefits, 25k cap), N+1 best-effort; ats-jobs `?details=true`
variant claims inline description — NOT verified (budget). No auth/browser.
Offline: no upstream workable test file (gap); ats-jobs node parse check
passed on synthetic body. Live probe: `apple` → 200 valid tenant
(`{"name":"Apple","jobs":[]}`, empty — ambiguous per emptyMeansExists=false);
`starling-bank` → 200, company "Starling", 104 rows / 49 unique shortcodes,
3 sample rows parsed fully. Request count: 2.
Decision: REUSE_AS_SOURCE_SPEC_V01 (catalog fits v0.1 exactly: single JSON,
jobs[], dotted paths, stable ID, len-based completeness; descriptions via
future detail phase as for all declarative sources).

## Description strategy (§15)

- BambooHR: listing has NO description; detail JSON has HTML description
  (no separate qualifications) → N+1 required for semantics.
- Teamtailor: FULL description inline in catalog (RSS and jobs.json) →
  no detail needed. Qualifications inside body, not separate.
- Workable: NO description in catalog; Markdown detail per shortcode
  (49 fetches for 104-row starling board) → N+1 required; multi-location
  rows share one shortcode (dedupe before enriching).

## Live safety (Wave 1 totals)

Companies probed: 6 tenant URLs (hp/detectify, canva/polestar,
apple/starling-bank — one per ATS per round, sequential, 3s pacing).
Total wire requests: 6 (3+3, budget max reached, no extras taken).
403: 0. 429: 0. CAPTCHA/challenge: 0. Retries: 0 (harness max_retries=0).
Browser: 0. Concurrency: 1. Proxy: 0. Brute-force: 0. Disproven HIGH rows:
canva/teamtailor (404), hp/bamboohr (empty), apple/workable (empty tenant).
Raw bodies: `external_reuse_audit/wave1_probes/*.body.bin` + status JSON.

## Wave 2 matrix (existing ATS, design only — no live tests yet)

| ATS | JobResearCHEF | ats-scrapers | ats-jobs | comparison available |
| Workday | adapter+fixture | scraper+3.5k seeds + cap-2000 note | endpoint+offset POST | yes |
| SuccessFactors | adapter+fixture | scraper+1.4k seeds | — | partial |
| SmartRecruiters | adapter+fixture | scraper+seeds | offset endpoint | yes |
| Greenhouse | adapter+fixture | scraper+6k seeds | endpoint | yes |
| Eightfold | spec (NVIDIA/MS) | scraper+84 seeds | — | partial |
| Lever | adapter+fixture | scraper+seeds | endpoint | yes |
| Ashby | adapter+fixture | scraper+3.4k seeds | endpoint | yes |
| Oracle | adapter+fixture | scraper+seeds | — | partial |
| Avature | adapter+fixture | scraper (+browserbase fallback, rejected) | — | partial |
| Phenom | adapter+fixture | code paths, no CSV | — | partial |
| Radancy | adapter+fixture | code paths, no CSV | — | partial |
| Google | CODE_ONLY (stale RPC) | HTML listing path | — | yes (candidate simpler path) |
| Apple | NEEDS_EXTENSION | CSRF→search→loader detail | — | yes |
| Meta | UNRESOLVED | cloakbrowser GraphQL (rejected) | — | reference only |

Future decision weights (§14): correctness, stable IDs, semantics,
min requests, anti-ban, deterministic pagination, failure semantics,
simplicity, test evidence, lifecycle fit — in that order.

## Verdict

READY_TO_REUSE (decisions made, no production code written in this Wave):
Workable catalog → SourceSpec v0.1 shape; Teamtailor + BambooHR → small
adapters reusing parsing shapes proven above; detail N+1 via existing
enrichment philosophy.ats-scrapers tenant CSVs for the three families
remain CANDIDATE seeds (mega-brand slug collisions disproven live for
canva/hp; per-tenant verification still required lazily).
