# MVP Definition-of-Done audit

Date: 2026-09-01
Result: **18/18 PASS**

This audit maps the original handover's Definition of Done to current authoritative evidence. A
passing test is cited only where its scope directly exercises the requirement; live-operation claims
also require persisted run evidence.

| # | Handover requirement | Result | Authoritative evidence |
|---:|---|:---:|---|
| 1 | Import master v1.5 correctly | PASS | Frozen SHA-256 and all six exact acceptance metrics pass in `milestone_1_validation.md`; clean reconstruction repeats the import. |
| 2 | Use Corporate Cluster ID and portal dedup | PASS | Relational `CorporateCluster`/`ClusterPortalMapping`/`Portal` model, normalized URL uniqueness and importer/registry tests; current state is 589 mappings over 524 active portals. |
| 3 | Start manually | PASS | Typer CLI exposes explicit local commands; no daemon, cron or required cloud service exists. |
| 4 | Scan a significant set of resolved career portals | PASS | Corrected representative run 26 scanned 100 portals: 92 success, 8 isolated failures, gate PASS. |
| 5 | Have real ATS adapters | PASS | Ten structured adapter families route 123 scannable portals; contract fixtures and bounded canaries are documented in adapter rollout reports. |
| 6 | Handle rate limiting/backoff | PASS | Global/per-host concurrency, interval, retry/backoff/jitter, `Retry-After`, request budgets, circuit breaker and 24-hour cooldown are configured and covered by offline HTTP tests. |
| 7 | Normalize vacancies | PASS | Deterministic normalizer feeds canonical jobs and is exercised through lifecycle/processing tests. |
| 8 | Filter cyber scope | PASS | Versioned YAML taxonomy and 212-case benchmark: 100% cyber accuracy. |
| 9 | Filter junior/intern scope | PASS | Configured exclusions plus experience/ordinal parsing; benchmark seniority accuracy 98.1%, above the 95% gate. |
| 10 | Filter vacancy geography | PASS | Configured target/excluded countries, aliases/codes and unknown-country distinction; benchmark 100%. |
| 11 | Deduplicate vacancies | PASS | Source identity, canonical apply URL, ATS ID and fingerprint order have dedicated cross-source tests. |
| 12 | Persist history | PASS | Immutable `JobObservation`, retained `SourceJob`, scan/import batches, registry audit and raw provenance fields are database-backed and tested. |
| 13 | Distinguish new/active/closed | PASS | Two-successful-absence lifecycle, no closure from failed/incomplete snapshots, reopening and reclassification are tested. |
| 14 | Produce run metrics | PASS | `ScanRun` persists duration inputs, requests, HTTP groups, retries, 429, discovered/new/updated/closed/duplicate and error evidence; the Runs view adds failed-domain/parser/empty diagnostics. |
| 15 | Show a consultable dashboard | PASS | Streamlit renders five operational tabs; `dashboard_analytics_validation_v2.md` proves all minimum metrics/filters and zero browser console errors. |
| 16 | Avoid mandatory fragile LinkedIn scraping | PASS | LinkedIn is an isolated, strict, checksum-idempotent manual CSV source; no login/CAPTCHA/anti-bot automation exists. |
| 17 | Test critical components automatically | PASS | 169 offline tests plus Ruff, benchmark, master validator, clean reconstruction, CI and recovery drill pass. |
| 18 | Isolate a single portal error | PASS | Scanner wraps every portal independently and persists partial evidence; dedicated tests prove another portal continues and timeouts are isolated. |

## Cross-cutting constraints

- The company universe, portal registry and vacancy observations remain separate layers.
- Master v1.5 remains checksum-identical; all corrections and Wave 6 are additive/versioned evidence.
- Geographies match the configured handover set; Italy is included, Middle East and New Zealand are
  excluded, and filtering is applied to vacancies rather than discovery geography.
- No people research, CV-fit, generic SWE expansion, senior-role expansion, GPU requirement,
  microservice/cloud dependency, proxy rotation, CAPTCHA/login bypass or generic browser scanner was
  introduced.
- Network operation remains manual, bounded and stop-on-gate. The policy reduces blocking risk but
  cannot guarantee continued access to third-party public endpoints.

## Roadmap reconciliation

All work packages 0-9 in `docs/ROADMAP.md` are checked and backed by named artifacts. The final audit
reconstructed v1.10 from v1.5 plus every versioned registry batch, reconciled both geography and
sector coverage to 12,503 rows, and proved exact SQLite restore. No required implementation item and
no P0/P1 risk remains open.

The remaining items are optional/trigger-based growth: resolve more unmapped clusters, convert more
fallback routes to contract-backed structured adapters, collect a reviewed production LinkedIn CSV
for cross-source measurement, and adopt migrations/scheduling/different persistence only when their
documented triggers are met.
