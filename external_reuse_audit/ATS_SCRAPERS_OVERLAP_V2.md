# ATS-Scrapers Overlap V2 (offline, canonical universe)

100% offline. Zero career-site HTTP, zero browser, zero probing, zero JobSeek,
zero modifications to JobResearCHEF or runtime/. Every output row carries
`verified=false, verified_at=null`: these are EXTERNAL SOURCE CANDIDATES,
never bindings. `JOBSEEK_DEFERRED_FOR_LICENSE_REVIEW` — no JobSeek data used.

Reproduce: `python3 external_reuse_audit/build_ats_scrapers_overlap.py
--universe JobResearCHEF/research_agent_v24/data/company_universe/
master_company_universe_v1_12_stripe_greenhouse.csv --ats-dir
external_reuse_audit/vendor/ats-scrapers/ats-companies --commit
6b44a1badc9bfbf5cf176f75265cc5729e520e99 --out-candidates
external_reuse_audit/ats_scrapers_external_candidates.csv --out-high
external_reuse_audit/ats_scrapers_high_confidence.csv --out-stats <file>`.
Stdlib only, no network imports, deterministic (rerun = byte-identical md5).

## 1. Canonical company dataset

- Path: `JobResearCHEF/research_agent_v24/data/company_universe/master_company_universe_v1_12_stripe_greenhouse.csv`
- Why canonical: newest versioned master (2026-09-02); declared "new synchronized
  master" in `docs/V2_IMPLEMENTATION_STATUS.md` (V23) and target of decision
  0044 (canonical-careers-URL vs operational-ATS-source, Stripe Greenhouse
  correction). Supersedes v1_5 (wave5, used by previous audit) through registry
  corrections run17/23/24/26/27 + wave6 + Stripe fix.
- Rows: 12,503. Unique Record IDs: 12,503 (= stable `internal_company_id`,
  e.g. EMP-00002). Unique normalized Employer: 12,503. Columns: 32, incl.
  Record ID, Employer, Canonical Employer, Parent Group, Corporate Cluster ID,
  Freeze Version (all `v1.0`), Discovery Geography, Corporate Website (EMPTY
  on all rows — domain evidence comes only from Resolved Corporate Website),
  Resolved Corporate Website / Careers Landing / Jobs Search URL (populated on
  1,277 rows ≈ 10%), ATS Family, ATS Confidence, Portal Resolution Status.
- No alias column (Parent Group / Canonical Employer used as name keys).
- Geography (Discovery Geography): Italy 1948, USA 1841, Germany 1039, Canada
  789, UK 581, Finland 562, France 547, Singapore 399, Netherlands 351,
  Switzerland 324, Australia 277, … — global, Italy/US/EU-weighted.
- Previous "Australia-centric" claim: **WRONG**. Australia is 11th (277 rows,
  2.2%). Likely cause: the old audit sampled bank/employer rows (AU banks are
  over-represented in early Record IDs) instead of the geography distribution.
- v1_5 vs v1_12 diff: identical ID set; only 37 rows differ (registry
  corrections, e.g. PayPal Taleo-style → Workday, Stripe → Greenhouse), so the
  old universe was superseded, not invalid.

## 2. ats-scrapers input (frozen vendor checkout, not re-cloned)

- Commit: `6b44a1badc9bfbf5cf176f75265cc5729e520e99` (2026-09-02, release v0.3.0).
- License: MIT (code; no separate dataset grant → attribution required on reuse).
- Tenant files: 47 CSVs. Total rows: 80,390.
- Schema: 42× `name,slug,url`; 1× `name,slug,url` (CRLF); eightfold adds
  `domain`; icims adds `company_name`; keka is `name,url` (slug derived from
  host); phenom is `url,name,company_code,locale,country` (slug=company_code,
  often empty). `slug` is the board identifier, `url` the public board link.

## 3. Matching (conservative, §4)

- HIGH_CONFIDENCE only with domain/URL evidence: URL_EXACT (our resolved portal
  == board URL, decisive), DOMAIN_EXACT (eightfold registry domain == our
  domain), SLUG_PLUS_NAME (board slug/host token == registrable-domain company
  token + compatible names; generic tokens like `jobs`, `career5`, `wd1`
  excluded; `jobs.netflix.com` → `netflix` via eTLD+1 logic — this exact bug
  produced 3,448 false rows in a first run and was fixed before writing outputs).
- CANDIDATE: NAME_EXACT (exact normalized name, no domain evidence, to inspect)
  or SLUG (token match, names differ, to inspect). Single-word collisions stay
  CANDIDATE by design, never HIGH.
- Rejected (counted, not stored): generic names (≤2 chars, 15 pairs), one
  external row matching >1 internal company (364 pairs, subsidiary/parent
  ambiguity). No aggressive fuzzy matching anywhere.

## 4. Results (unique companies, universe = 12,503)

- HIGH_CONFIDENCE companies: **562 (4.5%)**, 851 rows.
- CANDIDATE-only companies: **1,046 (8.4%)**, 1,748 rows.
- NO MATCH: **10,895 (87.1%)**.
- HIGH coverage: 4.5%. HIGH+CANDIDATE coverage: 12.9% (1,608 companies).
- External candidate rows total: 2,599 (851 HIGH + 1,748 CANDIDATE).
- Multi-source: 540 companies MULTI_SOURCE_CANDIDATE (439 multi-ATS, 152
  multi-tenant same ATS — e.g. regional + executive boards). Regional entities
  resolving to a global group board (e.g. Vodafone Romania → Vodafone) are kept
  distinct and need operator review before any binding.
- Ambiguous/rejected pairs: 379 (details in
  `ats_scrapers_match_rejections_summary.md`).

| ATS | HIGH companies | CANDIDATE rows | JobResearCHEF support |
|---|---|---|---|
| workday | 225 | 435 | LEGACY_SUPPORTED |
| successfactors | 120 | 77 | LEGACY_SUPPORTED |
| smartrecruiters | 103 | 133 | LEGACY_SUPPORTED |
| eightfold | 65 | 25 | DECLARATIVE_SUPPORTED |
| bamboohr | 58 | 131 | UNSUPPORTED |
| greenhouse | 49 | 126 | LEGACY_SUPPORTED |
| teamtailor | 44 | 35 | UNSUPPORTED |
| workable | 35 | 58 | UNSUPPORTED |
| lever | 16 | 80 | LEGACY_SUPPORTED |
| join_com | 14 | 68 | UNSUPPORTED |
| ashby | 12 | 76 | LEGACY_SUPPORTED |
| moka | 23 | 36 | UNSUPPORTED |
| others | ≤15 each | — | mixed |

## 5. Previous audit confronto → PREVIOUS_NUMBERS_PARTIALLY_WRONG

Old: 12,503 / HIGH 740 / CAND 792 / 5.9% / 12.3%. Differences: (a) old HIGH
mixed 592 jobseek-only + 96 joint website-domain matches into the headline —
excluded here by design; (b) old ats-scrapers component was URL-equality only
(148 companies incl. joint) vs 156 URL_EXACT companies now — that component is
CONFIRMED (delta explained by v1_5→v1_12 corrections); (c) new SLUG_PLUS_NAME
adds legitimately evidenced HIGHs (406 companies) the old method missed;
(d) old "Australia-centric" label was WRONG (§1). Same universe size by
coincidence of identical ID sets, not by same method.

## 6. JobResearCHEF readiness (HIGH rows: 851)

- LEGACY_SUPPORTED: 541 rows (63.6%) — usable in future with zero new code
  after lazy one-time validation (workday/SF/SR/greenhouse/lever/ashby/…).
- DECLARATIVE_SUPPORTED: 65 rows (7.6%, eightfold).
- UNSUPPORTED: 245 rows (28.8%, bamboohr/teamtailor/workable/…) — no universe
  demand now; candidates only.
- HIGH companies fully legacy-covered: 333; fully declarative: 30; mixed: 101;
  only-unsupported: 98.

## 7. Anti-ban policy (future lazy validation, NOT executed)

External candidates must REDUCE traffic, never generate it. Forbidden: batch
validation of HIGHs, full-universe validation, parallel validation, slug
brute-force, tenant scans, endpoint enumeration. Allowed only: on company-scan
need → single sequential one-time validation of that company's candidate →
persist binding if confirmed → cache permanently → immediate stop on
403/429/challenge. This task performed none of it (counters in chat report).

## 8. Files

- `ats_scrapers_external_candidates.csv` — 2,599 rows (HIGH + CANDIDATE).
- `ats_scrapers_high_confidence.csv` — 851 rows (HIGH only).
- `ats_scrapers_match_rejections_summary.md` — rejection summary.
- `build_ats_scrapers_overlap.py` — reproducible script.
