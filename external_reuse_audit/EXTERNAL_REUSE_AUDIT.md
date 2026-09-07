# External Reuse Audit — JobResearCHEF vs public ATS/source repos

**Date:** 2026-09-06. **Mode:** read-only (cloned 5 public repos shallow from
github.com; read code/README/CSV/tests/fixtures only). **Zero career-site HTTP,
zero browsers, zero scraper executions, zero probing.** No file in JobResearCHEF
or runtime/ was modified. Vendor checkouts live in `vendor/` (git-ignored
upstream checkouts, depth 1, frozen at audit date — re-clone to refresh).

## Repositories (verdicts)

| Repo | Verdict | One line |
|---|---|---|
| ats-scrapers (kalil0321) | HIGH_VALUE | 80k company→ATS seed rows (MIT) + protocol reference for Google/Apple/Eightfold/Workday |
| jobseek (colophon-group) | HIGH_VALUE | 7k company→board rows with ATS type + token triple (license check needed before bulk import) |
| ats-jobs (shunsukefuruyama) | MEDIUM_VALUE | Independent 12-provider endpoint table (MIT); confirms single-request + offset shapes |
| CareerScout (Ramcharan747) | LOW_VALUE | ATS URL templates only; runtime is brute-force at scale (rejected) |
| career-ops (career-ops-hq) | DEFER_TO_LATER | Applicant-side workflow system, not a source-ingestion asset |

## ats-scrapers (priority repo)

Dataset `ats-companies/`: 47 CSVs, 80,390 rows, schema `name,slug,url`
(some legacy files `name,url`). Fresh (HEAD 2026-09-02, v0.3.0). Code MIT,
no separate dataset grant found in repo → treat as MIT-with-attribution.

1. **Offline seed: YES, with provenance.** Import as seed candidates, never as
   authoritative bindings. Keep per-row: source repo + commit SHA + ATS file +
   original name/slug/url + import date. Our binding model stays
   operator-confirmed; external rows enter as `CANDIDATE` confidence.
2. **Importable fields as-is:** `slug` (board identifier), `url` (board URL),
   ATS family (= filename). Do NOT import `name` as canonical (free-form).
3. **Provenance/confidence:** `source=ats-scrapers@<sha>`, `confidence=CANDIDATE`,
   `verified_live=false`. Promotion to binding only after our own single probe.
4. **ATS overlap with our 11 legacy adapters:** greenhouse, lever, ashby,
   workday, smartrecruiters, successfactors, oracle, phenom, avature, radancy
   (no radancy CSV — covered via docs/code paths), plus workable/bamboohr/etc.
   not in our set (see crosscheck doc).
5. **ATS in ats-scrapers NOT in JobResearCHEF:** workable, bamboohr, breezy,
   recruitee, teamtailor, personio, rippling, icims, taleo, cornerstone,
   jobvite, ukg/dayforce/adp/paycom/paylocity, + regional (beisen, moka,
   gupy, herp, hrmos...). None needed now; candidates only if our universe
   demands them.
6. **v0.2-relevant code paths observed (reference only):** Workday tenant/
   instance/site triple handling + total-cap-2000 behavior; Eightfold
   `start=` offset + `data.count` (confirms our spec shape); Apple CSRF→search→
   `window.__loaderData__` detail with minimum/preferredQualifications;
   Google HTML listing (?page=N) + detail HTML.

Runtime techniques in-repo: per-tenant + per-job fan-out concurrency,
cloakbrowser stealth-Chromium fork + residential proxies (Tesla/Meta),
browserbase fallback (Avature) → all classified DO_NOT_REUSE_RUNTIME.
What we keep is PROTOCOL KNOWLEDGE + DATA, never the runtime.

## Google (§4)

Our GoogleCareersAdapter (Boq/batchexecute RPC, stale `r06xKb`): CODE_ONLY,
live behavior unverified. ats-scrapers GoogleScraper: plain HTML listing
`GET .../jobs/results?hl=en_US&page=N`, job links via stable
`aria-label="Learn more about <Title>"`, locations via Material icon chips
(`place`/`corporate_fare`), detail per job page meta tags — EXTERNAL_REFERENCE,
CURRENT_LIVE_VERIFIED=false. **CANDIDATE_SIMPLER_PATH documented:** the HTML
path avoids the stale-RPC problem entirely (page-number pagination, no opaque
op IDs, no positional arrays). Not implemented in this task. ats-jobs/CareerScout:
no Google support found.

## Apple (§5)

ats-scrapers AppleScraper confirms EVERY element of our Batch-2 finding:
CSRF bootstrap (`GET /api/v1/CSRFToken`, cookie+header, single session),
`POST /api/v1/search` JSON catalog page_size 20, full body split across
`description` / `minimumQualifications` / `preferredQualifications` in
`window.__loaderData__` detail JSON. Confidence increased for:
bootstrap_request (now 2nd independent implementation),
session-cookie persistence, separate qualifications paths,
HTML-embedded-JSON detail. (Their docstring also names `/api/v1/jobsTeam`;
constant used is `/api/v1/search` — matches our probe.) No Apple probing done.

## Meta (§6)

ats-scrapers MetaScraper: PROTOCOL KNOWLEDGE = GraphQL listing queries +
JSON-LD detail blocks, `fb_dtsg`-class browser-issued tokens required, no
public REST path. UNACCEPTABLE RUNTIME TECHNIQUE = cloakbrowser
stealth-Chromium + GraphQL interception (+ proxy env for Tesla path).
We learn the protocol shape; we adopt nothing that bypasses bot management.
Meta stays UNRESOLVED for deterministic HTTP harvesting.

## jobseek (§7)

Valuable ONLY as data + workflow reference. `companies.csv` (5,672 rows:
slug/name/website) + `boards.csv` (7,034 rows: company→board_url +
monitor_type + monitor_config token JSON + scraper_type). Example row gives
`workday/{company, wd_instance, site}` — the exact bootstrap triple our
Workday adapter scrapes from HTML. Use: company → known board/source
candidate WITHOUT live discovery. Onboarding workflow (`ws new/probe/select`)
is a sane operator-confirmed model, aligned with our binding philosophy.
Everything else (Typesense, Redis, Postgres deploy, web app, MCP):
IGNORE. License caution: code MIT, but LICENSE-JOB-DATA puts job-posting
collections under CC BY-NC 4.0 with attribution; registry CSVs sit in a grey
zone → REUSE_AS_REFERENCE + verify, no bulk import before a license check.

## CareerScout (§8)

Usable: 14-platform ATS URL templates + per-platform rate-limiter shapes
(10 rps) as REFERENCE. Rejected into DO_NOT_REUSE_RUNTIME: 200-worker career
finder, slug brute-forcing across 14 ATS APIs, Workday 4-env × 8-board
probing, eBPF/CDP engine, mass concurrency. Parser field map
(title/location/description per ATS) is MINOR reference at best — our
normalizer already covers it (KEEP_LEGACY_JOBRESEARCHCHEF).

## ats-jobs (§9)

MIT, zero-dependency, 12 providers, no browser/HTML/proxies by design —
the closest philosophy to ours. Endpoint table independently confirms:
single-request boards (Greenhouse/Lever/Ashby + 7 more),
SmartRecruiters offset (`limit=100&offset=`), Workday offset POST
(`{tenant}.wd{n}.../jobs?offset=`, body limit 20). Confidence increased for
single_request/unpaginated + offset pagination. Its `discover.js`
(parallel 12-provider probing per domain + robots.txt respect) stays
REFERENCE-ONLY: we do not adopt probing-as-runtime. Do not import the
library; the table is the asset.

## career-ops (§10): DEFER_TO_LATER

Applicant-side system (CV tailoring, application tracking, interview prep,
dashboards), MIT. `providers/` holds per-source fetchers but the value is
workflow/UX, not ingestion. Revisit only when building application tracking.

## Overlap with our company dataset (§11)

Our dataset: `master_company_universe…wave5.csv`, 12,503 companies
(Australia-centric). Conservative matching, no fuzzy binding creation:

- EXACT/HIGH (portal-URL equality vs ats-scrapers, or website-domain
  equality vs jobseek): **740 (5.9%)** — 52 ats-only, 592 jobseek-only, 96 both.
- CANDIDATE (normalized-name equality only): **792 (6.3%)**.
- NO MATCH: **10,971 (87.7%)**.
- Coverage HIGH: 5.9%; HIGH+CANDIDATE: 12.3%.
- Of 12,361 not-fully-resolved portals, 679 (5.5%) have an external hit.
- Top matched ATS: successfactors 108, workday 11, greenhouse 11, phenom 8,
  oracle 5, lever 2, eightfold 1. (Details + per-provider table in
  COMPANY_REGISTRY_OVERLAP.md.)
- No statistics invented: all counts from local files (script logic
  retained in that doc). Matches are NOT bindings.

## Licenses (§12)

| Repo | Code | Data/config | Rule for us |
|---|---|---|---|
| ats-scrapers | MIT | No separate grant → MIT-with-attribution assumed | learn ✓, copy w/ attribution ✓, import seed w/ provenance ✓ |
| jobseek | MIT | CC BY-NC 4.0 on posting collections; registry CSVs grey zone | learn ✓, bulk import ⏸ verify first + attribution |
| CareerScout | MIT | n/a (techniques) | learn URL templates ✓, runtime ✗ |
| ats-jobs | MIT | n/a (no dataset) | learn ✓ |
| career-ops | MIT | n/a | defer |

Learn ≠ copy ≠ import-dataset: only ats-scrapers seeds are cleared for
import (as CANDIDATE with provenance); jobseek boards need a license check.

## TOP 5 reuse opportunities (§13)

1. **ats-scrapers tenant CSVs as offline seed** — 80k company→ATS rows;
   LOW effort (CSV import as CANDIDATE + provenance), ban risk NONE (offline).
2. **jobseek boards as board-candidate source** — ATS type + token triple
   (esp. Workday tenant/instance/site); LOW effort post-license-check, NONE.
3. **Google HTML path as CANDIDATE_SIMPLER_PATH** — replaces stale-RPC
   approach when Google is scheduled; MEDIUM effort, LOW ban risk (page-number
   HTML, sequential). Not now.
4. **Apple loader-state detail shape as reference** — confirms separate
   qualifications + embedded-JSON capability for v0.2 design; LOW (doc only).
5. **ats-jobs endpoint table as crosscheck** — independent confirmation of
   single-request + offset shapes; LOW (already folded into crosscheck doc).

## TOP 5 things to ignore

1. cloakbrowser/stealth/proxy paths (Meta/Tesla) — ban-risk incompatible.
2. CareerScout brute-force probers + 200 workers + eBPF/CDP engine.
3. ats-scrapers fan-out concurrency + per-job detail concurrency as runtime.
4. jobseek infra (Typesense/Redis/Postgres deploy/web/MCP) — we have DB+dashboard.
5. career-ops applicant workflow (revisit only for application tracking).

## Source-resolution strategy (§14): YES_MODERATE_IMPACT

Replacing "Hermes discovery for everything" with "external registries offline
→ known adapters/specs → Hermes only unresolved" is realistic and moderately
impactful: external seeds cover ~6–12% of our universe at HIGH/CANDIDATE
confidence (Australia-centric universe vs US/EU-tech registries explains the
ceiling), each seed still needs one operator-confirmed probe before becoming
a binding, and aggressive runtime techniques are excluded throughout. The win
is bounded discovery work, not zero discovery work.

## Safety & integrity

Live career-site HTTP: 0. Browser calls vs career sites: 0. Brute-force: 0.
Scrapers executed: 0. JobResearCHEF modified: 0 files. runtime/ modified: 0
files. New files: this doc + 2 companions + vendor/ checkouts.
