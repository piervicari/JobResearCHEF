# Stapply + facet integration audit — 2026-09-09

AUDIT / DESIGN / MEASUREMENT only. Nothing below is implemented. No runtime
integration, no V25 mutation, no adapter ports, no schema migration, ADR 0064
stays PROPOSED. Non-negotiable rule honored: ALL locations and ALL job
categories in scope; facets are partitioning/planning/metadata only and MUST
NOT decide whether a job is ingested.

## 1. Stapply current dataset (live manifest, 1 wire, 41 KB)

- Manifest: `https://storage.stapply.ai/jobhive/v1/manifest.json`, version
  `2.0`, generator `ats-scrapers/0.3.0`.
- `generated_at: 2026-09-08T14:30:04Z` (single observation — see section 4).
- 65 source families, 80,390 companies, 5,141,962 jobs (5,887,105 raw
  pre-dedup). Sums verified: per-ATS rows add to 5,887,105.
- Formats: per-ATS `jobs.csv` + `jobs.parquet` (+ sha256), global
  `all.csv` (16.8 GB) / `all.parquet` (2.25 GB), `companies.csv` (6.9 MB),
  per-ATS `companies.csv` directories. `by_date` deltas: EMPTY (none
  published). Full-slice sizes: workday CSV 4.48 GB, greenhouse 1.12 GB,
  successfactors 1.37 GB, smartrecruiters 1.39 GB; tiny: eightfold 53 MB,
  phenom 86 MB, avature 14 MB.
- Company directory columns: `ats,name,slug,url` (+ `domain` on eightfold).
  Job schema v2.0: 26 columns — `url,title,company,ats_type,ats_id,
  location,country_iso,region,language,lat,lon,is_remote,salary_min/max/
  currency/period/summary,employment_type,department,team,description,
  posted_at,requisition_id,apply_url,commitment,raw`.
  IDs: `global_id = {ats_type}:{ats_id}` (first-colon split); UUID4 fallback
  when `ats_id` missing. Timestamps: per-job `fetched_at` exists in schema
  (fill varies, see section 3); no `scanned_at`; no per-provider timestamps
  in manifest (rows/size/sha only).
- Code license: MIT (`kalil0321/ats-scrapers`, vendored pin `6b44a1b` =
  v0.3.0, matches manifest generator). Dataset reuse terms: NO separate
  data license found in README/docs — code is MIT, dataset redistribution
  terms UNCERTAIN (reuse as read-only reference + candidate directory;
  do not republish rows). Uncertainty recorded, not resolved here.

## 2. CORE/V25 reconciliation (offline, 0 ATS wires)

V25 `tier_s_operational_sources_v1.csv` (237 rows) vs Stapply company
directory (80,390 rows), exact-name + company-specific-host match (shared
ATS hosts excluded). Heuristic noise acknowledged: name variants inflate
NOT_FOUND; case-only diffs inflate URL_DISAGREEMENT.

| class | n |
|---|---|
| AGREE | 15 |
| STAPPLY_NEW_CANDIDATE | 94 |
| NOT_FOUND | 87 |
| MULTIPLE_SOURCE_DOORS | 19 |
| ATS_DISAGREEMENT | 12 |
| URL_DISAGREEMENT | 10 |
| OUR_SOURCE_POSSIBLY_STALE | 0 confirmed (candidates listed below) |
| AMBIGUOUS_MATCH | 0 (heuristic limits; multi-ATS names folded into MULTIPLE_SOURCE_DOORS) |

- AGREE (15, all same-family same-URL): CrowdStrike-WD, Datadog/Okta/
  Anthropic/MongoDB/Elastic/GitLab/Dragos/GuidePoint/Glean/OneTrust/
  TogetherAI-GH, Palantir/Sysdig-Lever, Vanta-Ashby.
- STAPPLY_NEW_CANDIDATE (94, V25 family empty + Stapply door): Cisco→
  phenom/workday, Zscaler→greenhouse, Broadcom→workday, Fortinet→oracle,
  Netskope→greenhouse, Helsing→greenhouse, Meta→smartrecruiters,
  Amazon→breezy/personio (latter two look like junk mirrors — see
  INTELLIGENCE_ONLY), Apple→workable. Full queue in script output; candidates
  ONLY, no auto-promotion (ADR 0057 pattern via ExternalSourceCandidate).
- URL_DISAGREEMENT (10): mostly case-only (Proofpoint `ProofpointCareers`
  vs `proofpointcareers`, ServiceNow `Visa` vs `visa`, Stripe/Dragos API-vs-
  board host) → normalization, not re-resolution. JPMorgan Oracle is a
  host→site-path refinement (`jpmc.fa.oraclecloud.com` vs `.../CX_1001`;
  tenant is SSO-walled regardless).
- ATS_DISAGREEMENT (12, possible-stale queue, direction UNKNOWN without
  live re-resolution): Blue Origin WD vs lever, Wiz GH vs ashby, Airbus WD
  vs bamboohr, Booz Allen WD vs avature, Deutsche Bank WD vs
  smartrecruiters, Allianz SF-RMK vs phenom, Siemens Avature vs teamtailor,
  Cerebras Ashby vs greenhouse, Google custom-RPC vs breezy (junk).
- MULTIPLE_SOURCE_DOORS (19): NVIDIA workday+eightfold (known, already
  canonical+alternate in V25), Microsoft eightfold+smartrecruiters,
  Cloudflare/SpaceX/Discord/Databricks/Adyen/Forter gh+sr, Visa sr+wd,
  OpenAI ashby+bamboohr, Mastercard phenom+sr, Oracle CX_1+jobsearch
  (same family, two site paths).
- NOT_FOUND (87): Palo Alto, IBM, Check Point, Rapid7, Abnormal,
  Lockheed (Radancy — Stapply has NO radancy family), SentinelOne/
  Tenable/Panther/Pure/Veeam (GH names absent under those spellings),
  Amex (wildcard host), Porsche/Lockheed (host-only records).

Prioritized validation queue: (1) 12 ATS disagreements (live re-resolve,
cheapest first: Cerebras, Wiz, Blue Origin); (2) 19 multi-door (classify
canonical/alternate/mirror per section 10); (3) HIGH-value new candidates
(Cisco, Zscaler, Broadcom, Fortinet, Netskope); (4) case-only URL
normalizations (zero-wire).

## 3. Bootstrap feasibility (offline samples, 10–20 company-equivalents)

Head-slice fill rates (rows sampled per ATS; WD/GH/SR/Oracle/SF samples in
thousands due to Range-ignored responses — see Safety):

| ats | ats_id | title | loc | dept/team | posted_at | requisition | apply_url | description |
|---|---|---|---|---|---|---|---|---|
| greenhouse | 100% | 100% | 100% | 99%/0% | 100% | 96% | 0% | 100% |
| lever | 100% | 100% | 100% | 64%/100% | 96% | 0% | 96% | 100% |
| ashby | 100% | 100% | 100% | 100%/100% | 95% | 0% | 95% | 100% |
| smartrecruiters | 100% | 100% | 100% | 100%/34% | ~100% | ~100% | ~100% | ~100% |
| workday | 100% | 100% | 99% | 0%/0% | 0% | 98% | 0% | ~100% |
| eightfold | 100% | 100% | 100% | 0%/0% | 92% | 0% | 0% | 100% |
| oracle | 100% | 100% | 100% | ~0%/0% | ~100% | 0% | 0% | 92% |
| successfactors | 100% | 100% | 100% | 57%/0% | 0% | 0% | 0% | ~100% |
| phenom (n=10) | 100% | 100% | 100% | 100%/0% | 90% | 90% | 0% | 100% |
| avature (n=16) | 100% | 100% | 12% | 6%/0% | 0% | 6% | 0% | 88% |

Identity semantics vs JRC (critical): Stapply Workday `ats_id =
bulletFields[0] or externalPath-tail` (workday.py:502-503) — the EXACT
logic behind JRC's P0 badge-ID defect (Intel/Thales, fixed 2026-09-09).
Stapply has NOT fixed it upstream. Oracle `ats_id` is a `host:reqnum`
composite, not the native requisition. JRC identity (requisition-shape +
externalPath) is STRICTER than Stapply's.

Classification: greenhouse EXACT_NATIVE_COMPATIBLE (sample);
ashby/lever/smartrecruiters/successfactors/phenom/avature
TRANSFORMABLE_COMPATIBLE; eightfold/oracle URL_RECONCILIATION_REQUIRED;
workday UNSAFE as-is (badge tenants; posted_at/dept empty).

Schema impact: NONE. SourceJob already holds `source, source_job_id,
native_source_job_id, ats_job_id, requisition_id, raw_*,
posted_at/fetched_at, adapter, payload_sha256, raw_payload_json` — a
`STAPPLY_BOOTSTRAP` record fits with `source="stapply_bootstrap"`,
adapter=`stapply_bootstrap:<ats>`, full Stapply row in `raw_payload_json`.
No migration. Do NOT import into production (this audit wrote nothing).

## 4. Cadence / freshness (public evidence only)

- Actual publication schedule: NOT KNOWABLE from public evidence. ONE
  observation: `generated_at 2026-09-08T14:30:04Z`. Publisher code
  references "cron publish" races but the public repo ships NO dataset
  publish schedule (only `live-e2e` cron 05:00 UTC + ats-companies
  publisher). Do NOT infer daily-at-14:30.
- Schedule public? NO.
- `generated_at` semantics: snapshot build completion (manifest rewrite at
  publish; FileEntries carry no per-artifact timestamps).
- `fetched_at`/`scanned_at`: per-JOB `fetched_at` exists (fill: GH/LV/SR/
  Oracle/EF ~95-100%, WD/SF 0%, Avature 0%). No per-provider or per-company
  freshness anywhere in the manifest.
- Same-day signal verdict: NEEDS_MORE_OBSERVATIONS.
- Proposed flow (08:00 direct scan → later tiny manifest check → compare
  tracked companies → direct-verify only missing/new): manifest check is
  CHEAP (41 KB) and safe to observe for 7–14 days to learn the real
  cadence; the COMPARE step has no cheap read path (section 6), so the
  flow as designed is NOT yet executable. MORE_EVIDENCE before any watcher.

## 5. Same-day signal — see section 4 (verdict NEEDS_MORE_OBSERVATIONS).

## 6. Extraction cost

- Manifest 41 KB: CHEAP. Company dirs (~2.3 MB for 13 CORE families,
  6.9 MB global): CHEAP.
- Per-company job extraction: NO per-company artifact exists. The
  `Client.search()/load(ats=)` path downloads the FULL per-ATS slice into
  pandas (`pd.read_csv` of the whole file): workday 4.48 GB CSV,
  greenhouse 1.12 GB → EXPENSIVE/NOT_VIABLE for large families;
  ACCEPTABLE only for tiny ones (eightfold 53 MB, avature 14 MB, phenom
  86 MB). Byte-range reads work on some slices (206) but the CDN ignored
  Range on 5/9 slices (200 full). Per-company extraction verdict:
  NOT_VIABLE via slices; needs a server-side per-company endpoint that
  does not exist.
- Live re-scrape via Stapply scraper classes: same front doors as JRC,
  same wire costs, plus retries/backoff JRC forbids (retries=0) → no
  savings; reference value only.

## 7. Facet / server-filter matrix (code-read, 0 live wires)

| provider | verdict | dimensions (server) | counts? | multi? | membership in payload? | subdivision useful? | ordering useful? |
|---|---|---|---|---|---|---|---|
| Workday | TRUE_FACET | jobFamilyGroup, timeType, locations, workerSubType (+fallback highest-cardinality) via `appliedFacets` | YES (`facets[].values[].count`) | YES (workerSubType multi-tag; dedup absorbs) | PARTIAL (dept via jobFamily rollup in `raw`) | YES | YES |
| Eightfold/PCSX | SERVER_FILTER_ONLY | free-text `query`, `location`, `sort_by` — no facet params in scraper or JRC spec (start-only) | total only | n/a | NO (dept/team empty in slice) | NO (no partition axis) | MAYBE (timestamp sort unproven) |
| Oracle | UNRESOLVED | finder API may support query filters; NEITHER codebase uses any | total only | n/a | PARTIAL (Department/Org/Unit → dept) | UNRESOLVED | NO evidence |
| SmartRecruiters | NONE (observed) | limit/offset only in both codebases | totalFound only | n/a | YES (department.label, team; 100%/34%) | NOT_NEEDED (total-guarded, pages of 100) | NO evidence |
| SuccessFactors | UNRESOLVED | RMK HTML has server search facets; JRC never completed a walk; Stapply maps category→dept | n/a | n/a | PARTIAL (category/function) | UNRESOLVED | NO evidence |
| Greenhouse | NONE | single-shot, no params | n/a (response IS catalog) | n/a | YES (departments[] multi — overlap PROVEN) | NOT_NEEDED | YES (dept arrays) |
| Lever | NONE | skip/limit only; short-page end | none | n/a | YES (categories dept/team/commitment) | NOT_NEEDED | YES |
| Ashby | NONE | single-shot | n/a | n/a | YES (department string) | NOT_NEEDED | YES |
| Google custom | NONE | fixed 20/page RPC | total churns | n/a | location/rpc fields | NOT_NEEDED | NO evidence |

Overlap / multi-membership (all-locations/all-categories rule intact):
Stapply `workerSubType` sums EXCEED totals (multi-tag); GH jobs carry
multi-`departments[]`; dual-door companies (NVIDIA, Microsoft, Visa…)
prove one catalog ≠ one door. Facets PARTITION only under dedup; never
assume disjointness. Traversal rule: cover ALL values of the chosen
dimension; optimization = dimension CHOICE, not value skipping.

## 8. Workday >2K completeness — HIGH PRIORITY

Stapply mechanism (vendored `scrapers/workday.py`, code-read):
- Cap: `limit>20 → 400`; per-query reported total capped at EXACTLY 2000;
  past offset=2000 pagination WRAPS to page 1. Detection: `total ==
  QUERY_TOTAL_CAP (2000)`.
- Subdivision: recursive `_exhaust_query(applied_facets, depth)`; first
  facet `jobFamilyGroup`, then `timeType`, `locations`, then
  `workerSubType`; dynamic fallback = highest-cardinality remaining facet
  from live `facets[].values[].count` (counts-based planning, no extra
  probes). `len(values)<2` or already-applied facets skipped.
- Dedup: `ats_id or url` set-absorb across branches (overlap-safe).
- Termination: `MAX_SUBDIVISION_DEPTH=4`; capped-leaf accepts ≤2000 and
  stops (bounded loss, explicit).

JRC status (`sources/ats/workday.py`): sends `appliedFacets: {}` ALWAYS,
no total==2000 check, pins page-1 total, `natural_end = offset+len >=
total`. With page budget ≥100 a capped board walks 100×20, hits
`1980+20>=2000`, breaks with **`is_complete_snapshot=TRUE`** on a
truncated+possibly-wrapped catalog.

Verdict: YES — current JRC CAN silently mark a >2K capped board complete.
P0 candidate: YES (gates ANY future full-traversal/bulk Workday work;
default `max_pages_per_portal=30` accidentally bounds routine scans to
600, but bounded scans never close — the hole opens exactly when we
raise budgets). Do NOT implement here. Dynamic counts-based dimension
choice (Stapply `_pick_subdivision_facet`) is directly reusable at design
time — MORE_EVIDENCE for the design, ADOPT the principle (traverse all
values; choose dimensions by live counts).

## 9. Missing adapter candidates (CORE-relevant only)

JRC serves: workday, greenhouse, lever, ashby, smartrecruiters, oracle,
successfactors_rmk, teamtailor, workable, avature, phenom, radancy,
google_careers + declarative eightfold/beesite. Stapply has 65 families.

| candidate | class | CORE evidence | endpoint/protocol (Stapply ref) | identity | effort |
|---|---|---|---|---|---|
| BambooHR | PORT_CANDIDATE_HIGH | 11 V25 names (Cribl, Airbus-bamboohr door…) | `embed2.php` catalog + `/careers/{id}/detail` (matches JRC matrix note) | posting id | SMALL (adapter new; protocol known; needs non-empty validation FIRST per matrix) |
| iCIMS | PORT_CANDIDATE_MEDIUM | 3 (Lloyds, General Dynamics +1) | JSON feed endpoints (ref only) | job-id-from-URL pattern | MEDIUM |
| Cornerstone (CSOD) | PORT_CANDIDATE_MEDIUM | 3 (BBVA, Bitdefender +1) | `csod.com/ux/ats/careersite` JSON (ref only) | TBD | MEDIUM |
| breezy/personio/join_com/pinpoint/moka/rippling | NOT_NEEDED_NOW | ≤4 names each; google/amazon rows look like junk mirrors | — | — | — |

No ports executed. BambooHR stays gated on a non-empty live observation.

## 10. Source canonicalization (design, NOT implemented)

Roles: DIRECT_CANONICAL (one official door scanned routinely) /
DIRECT_ALTERNATE (second proven-same-catalog door, never parallel-scanned;
precedent: `nvidia_workday` + `nvidia_eightfold` V25 note) / MIRROR
(same postings via aggregator door, e.g. company.smartrecruiters.com
duplicates of a GH board — verify then demote) / AGGREGATOR_FALLBACK
(last-resort, never canonical) / INTELLIGENCE_ONLY (directory-level hints
such as breezy/personio rows for Google/Amazon — never scanned, never
promoted). Rules: official ATS door wins; same-catalog proof required
(detail applyUrl or id-overlap) before ALTERNATE/MIRROR; no
company-specific hacks — roles live on the source record, evaluated by
the existing preflight/routing path.

## 11. Drift / fallback / cross-check (design, NOT implemented)

A. Drift detection: VIABLE — weekly offline diff of V25
operational_url+family vs Stapply company dirs (0 ATS wires, ~9 MB);
mismatches → validation queue, NEVER auto-mutate V25. ADOPT the design.
B. Fallback for blocked sources: REJECT for SSO walls (JPMorgan-class —
Stapply scrapes the same front door; no bypass value). MIRROR fallback
only where same-catalog proof exists (NVIDIA precedent). Fallback engine:
MORE_EVIDENCE.
C. Completeness cross-check: VIABLE as design — compare per-company
Stapply row counts vs OUR DB for tracked companies; investigate deltas
by DIRECT re-scan only. Blocked today by section 6 (no cheap per-company
read). ADOPT the design, MORE_EVIDENCE for execution.

## 12. Recommended architecture impact (no status promotions)

- No ATS validation status changes from Stapply evidence alone (matrix
  rule upheld — nothing promoted in this audit).
- V25 gains NO new sources; the validation queue (section 2) feeds the
  existing sync/probe path when scheduled.
- Scan Architecture V2: Workday subdivision becomes a designed component
  (cap-guard + counts-based dimension choice); canonicalization roles
  become record-level fields in a future V25 schema rev (not this task).
- Facet observations: no SourceJob migration; IF needed later, store
  `(dimension, value, provenance∈{JOB_PAYLOAD,QUERY_BRANCH})` triples in
  `raw_payload_json` under `facet_obs` (smallest representation).

## 13. Unresolved questions

1. Real Stapply publication cadence (needs 7–14 d manifest observation).
2. Dataset redistribution terms (no data license found).
3. `fetched_at` provenance per ATS (scrape-time vs posted-time? WD/SF
   empty — why?).
4. Oracle/SF server-filter existence (UNRESOLVED axes).
5. Whether Stapply per-company job endpoints will ever exist.
6. BambooHR non-empty board (pre-existing JRC gap, unchanged).
7. Upstream fix for Stapply Workday badge-ID logic (still
   `bulletFields[0]` at v0.3.0).

## 14. Exact next task (NOT executed)

Workday cap-guard DESIGN doc: `total==2000` detection + counts-based
facet-subdivision plan (Stapply order as default, dynamic fallback) +
false-complete regression test using a synthetic capped fixture (0 live
wires). Then: implement behind the existing scanner path with
concurrency 1 / retries 0. ADR 0064 acceptance stays out of scope until
that design lands.

## Decision output

| role | verdict |
|---|---|
| Stapply registry intelligence | ADOPT (candidates only, ADR 0057 pattern, never auto-promote) |
| initial bootstrap | MORE_EVIDENCE (identity unsafe on WD; posted_at gaps; no cheap per-company path) |
| adapter-reference reuse | ADOPT (established ADR 0060/0061 pattern; bamboohr/icims/cornerstone queued) |
| fallback | MORE_EVIDENCE (REJECT for SSO walls; mirror only with same-catalog proof) |
| ATS drift detection | ADOPT (design: weekly offline diff, validation queue, no auto-mutate) |
| source canonicalization | ADOPT (design: 5 roles, record-level, no company hacks) |
| quality cross-check | ADOPT (design) + MORE_EVIDENCE (execution blocked on per-company reads) |
| same-day snapshot signal | MORE_EVIDENCE (7–14 d manifest watch; flow not yet executable) |
| facet subdivision | MORE_EVIDENCE (design next; Workday P0 candidate confirmed) |
| dynamic facet planning | MORE_EVIDENCE (counts-based choice sound; needs design) |
| facet metadata storage | MORE_EVIDENCE (triples-in-raw_payload recommendation; no migration) |

ADR 0064: NOT accepted (stays PROPOSED).

## Safety / validation

- ATS wires: 0. Retries: 0. LLM calls: 0. Browser/proxy/bypass: none.
- Canonical DB untouched; legacy unused; V25 registry unmodified (read-only).
- Stapply transfer: ~9.4 MB intentional (manifest 41 KB + company dirs
  8.7 MB + 5 small range slices ~0.4 MB) PLUS ~508 MB accidental: the CDN
  ignored HTTP Range on 5 large job slices (200 instead of 206) — files
  deleted from /tmp immediately after sampling fill rates; budget
  exceeded, cause recorded; NOTHING committed (no datasets/raw
  bodies/caches in repo).
- No runtime integration enabled; no schema changes; no production writes.
