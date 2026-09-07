# external_reuse_audit/ — offline/external ATS reuse evidence (NOT runtime)

Purpose: evidence for reusing external ATS protocol/parser knowledge
(primarily `ats-scrapers`, secondarily `ats-jobs`) inside JobResearCHEF
without importing external runtimes. Nothing here executes in production.

## Layout

- `vendor/` — frozen external checkouts, reference only:
  `ats-scrapers @ 6b44a1b` (2026-09-02, MIT),
  `ats-jobs @ 9edd4a6` (2026-08-26, MIT).
  NEVER add these as runtime dependencies. NEVER execute their provider
  discovery, concurrency, proxy, stealth/browser, or brute-force systems.
- `wave1_probes/` — saved bodies + status JSON from controlled live probes
  (sequential, JobResearCHEF HttpFetcher, retries 0, stop on 403/429).
- `ats_scrapers_*.csv`, `ats_reuse_wave1_*.{csv,json}` — derived audit data
  (company overlap, HIGH-confidence candidates, probe matrix).
- `wave1_probe_round*.py` — audit-only probe scripts. Not production code.
- `ATS_REUSE_WAVE1.md` — Wave 1 audit/test results (historical;
  implementation choice superseded by `ATS_REUSE_WAVE1_1.md`).
- `ATS_REUSE_WAVE1_1.md` — current protocol decisions (Teamtailor JSON,
  Workable `?details=true`, BambooHR pending).
- `EXTERNAL_REUSE_AUDIT.md`, `COMPANY_REGISTRY_OVERLAP.md`,
  `ATS_CAPABILITY_CROSSCHECK.md`, `ATS_SCRAPERS_OVERLAP_V2.md` — audit evidence.

## Production lives elsewhere

Reuse outcomes land as house-style adapters in
`../research_agent_v24/src/research_agent/sources/ats/`
(e.g. `teamtailor.py`, `workable.py`) with fixtures in
`../research_agent_v24/tests/fixtures/`. This directory only documents
WHY a protocol was chosen.

## Network rule

External runtime behaviors — provider fan-out, concurrency, proxies,
stealth/browser, brute-force tenant probing, CAPTCHA bypass — are NOT
inherited. All live probes use the JobResearCHEF safety stack
(HttpFetcher budgets, pacing, circuit breaker) and stop immediately on
403/429/challenge.

## Provenance requirement

Every reused protocol/parser fact must record: repo + commit SHA +
source file + license. Verbatim copies additionally preserve attribution
per the MIT license terms.
