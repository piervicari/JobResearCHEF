# Project status

Updated: 2026-09-01

## Milestone 1 - Complete and accepted

The authoritative master remains unchanged and passes all frozen acceptance checks: 12,503 rows,
12,503 unique record IDs, 11,798 corporate clusters, 1,263 resolved rows, 575 resolved clusters and
510 deduplicated operational portal URLs. The source SHA-256 is
`bae44ad9ab0a5800bec884b43fc236506d9da3ea51f72477830e5023fa81e7df`.

See `docs/reports/milestone_1_validation.md` for the regenerated report.

## Scanner and safety boundary - Complete for bounded manual operation

- Live scans require explicit portal IDs, a stable-order limit or deliberate `--all` opt-in.
- Public-address validation is applied before every request and redirect; URL credentials, private
  destinations and HTTPS downgrades are rejected by default.
- Request, redirect, response-size, retry, server-directed delay and overall-run budgets are bounded.
- Every live CLI scan creates an integrity-checked SQLite backup by default.
- A post-fetch gate prevents excessive failures, retries, `429` responses or unexpected complete
  empty snapshots from advancing lifecycle state.
- New scans persist adapter warnings and snapshot completeness per portal attempt. Existing databases
  receive the `warnings_json` column through the additive SQLite bootstrap; historical warnings are
  not synthesized during migration.
- Incomplete, generic and failed snapshots cannot close jobs; complete closure still requires two
  successful absences.

The remaining DNS re-resolution limitation is documented in `SECURITY.md` and ADR 0007.

## Sources and routing

Current scannable routing after the versioned corrections and Wave 6:

| Adapter | Portals |
|---|---:|
| SuccessFactors Recruiting Marketing | 55 |
| Phenom | 24 |
| Workday | 16 |
| Greenhouse | 11 |
| Radancy / TalentBrew | 7 |
| Oracle Recruiting Cloud | 4 |
| Avature | 2 |
| Lever | 2 |
| Ashby | 1 |
| SmartRecruiters | 1 |
| Conservative official HTML fallback | 369 |

This is 123 structured routes and 369 incomplete fallback routes. Routing is not the same as current
live availability. The new adapters have sanitized fixtures, pagination/schema tests and bounded
live canaries; the evidence is in `docs/reports/adapter_rollout_2026-08-31.md`.

LinkedIn remains a strict, checksum-idempotent manual CSV input. There is no login automation,
authenticated scraping or anti-bot bypass.

## Filtering, deduplication and lifecycle

- Cyber, seniority and vacancy geography are deterministic, configured and auditable.
- The versioned 212-case taxonomy benchmark passes a 95% component/final gate: cyber 100%, seniority
  98.1%, geography 100% and final decision 100%.
- Generic SWE, explicit senior roles, non-target functions and out-of-scope geographies are excluded;
  ambiguity is retained as `REVIEW`.
- Experience ranges and ordinal levels are interpreted conservatively; unknown structured countries
  remain `REVIEW` instead of being treated as known out of scope.
- External company aliases are provenance-backed and status-controlled. Only verified exact aliases
  resolve automatically; fuzzy matching produces read-only proposals.
- Reclassification is offline and preserves source provenance.
- Current database state after run 29: 5,789 active source jobs and 48 active canonical jobs, all
  currently `REVIEW`.

## Progressive rollout result

- Structured canaries: Ferrari/SuccessFactors, Proofpoint/Workday, PwC Italy/Phenom,
  Oracle Candidate Experience and MetLife/Avature completed without retry or `429` responses after
  fixture-led parser corrections.
- Generic coorte 25, final run 16: 23 successi, 2 fallimenti, 51 richieste, zero retry/`429`, gate
  PASS at 8% failure and zero closures.
- Corrected coorte 50, run 22: 47 successi, 3 fallimenti, 117 richieste, 3 retry, zero `429`, gate
  PASS at 6% failure.
- Initial coorte 100, run 23: gate FAIL at 27% failure and one `429`; processing was skipped and live
  expansion stopped while routes and pagination were remediated.
- Corrected representative coorte 100, run 26: 92 successi, 8 fallimenti, 360 richieste, zero retry
  and zero `429`; gate PASS at 8% failure with zero unexpected empty snapshots.

The eight residual run 26 access failures were suspended without bypass. Full evidence is in
`docs/reports/scan_scale_validation_v1.md`.

## Browser decision

Playwright is not used and is no longer a dependency. The observed residuals were DNS/URL staleness,
robots denial, HTTP 403 or anti-bot challenges rather than demonstrated JavaScript-rendering needs.
ADR 0008 records the decision and the conditions for any future reconsideration.

## Operator dashboard

The local Streamlit dashboard now provides an actionable review queue, job/source lifecycle
confidence, portal warnings and access/cooldown state, operational issue categories, adapter coverage
and a high-value unresolved-cluster view. It also exposes active/recent/closed job counts, all six
required job breakdowns, source overlap, geography/sector/ATS coverage, per-run HTTP/anomaly
diagnostics and the complete handover filter set. The dashboard browser is used only for local
operator UI; it is not a scanner fallback. The latest rendered validation is recorded in
`docs/reports/dashboard_analytics_validation_v2.md`.

## Portal Resolution Wave 6

Wave 6 uses a deterministic six-component score over unresolved clusters. Exactly 100 unique
clusters were selected. Fifteen received reviewed official corporate, careers and jobs endpoints;
the remaining 85 were explicitly deferred without emitting a registry change. Ambiguous acronyms,
organizational units, country-specific parent sharing and the recent CyberCX acquisition were not
forced into a mapping.

The synchronized state now has 1,277 resolved records, 589 resolved clusters and 524 active registry
portals. The distributable package contains the selection, reviewed decisions, 100-row wave and audit
artifacts, versioned ADD batch, summary and v1.10 master. Historical v1.5 remains checksum-identical.

## Verification snapshot

- `uv run pytest -q`: 169 passed.
- `uv run ruff check .`: PASS.
- `uv run research-agent validate-master`: PASS.
- `uv run research-agent benchmark-taxonomy`: PASS.
- `bash scripts/final_audit.sh`: PASS from a disposable empty database, including v1.5 import, all
  versioned registry batches, aliases, acceptance gates, dashboard queries, backup and recovery.
- SQLite working database and final retained backup: `integrity_check = ok`; the recovery copy matched
  SHA-256 and every user-table count exactly.
- `.github/workflows/ci.yml` performs the same offline reconstruction and recovery gates on pushes and
  pull requests without third-party network scans.

Backup retention was exercised after exact dry-run review: 19 historical databases and two associated
sidecars were removed, 1,089,814,528 bytes were reclaimed and the three newest verified backups were
retained. Generated databases, caches, backups and local environment settings remain ignored.

## Delivery state and next growth areas

The ordered MVP roadmap is complete and no P0/P1 item remains open. The next work is measured P2
growth rather than required hardening: increase structured coverage among the 369 incomplete
fallback routes, resolve more of the 11,209 unmapped clusters in reviewed waves and measure
official/LinkedIn cross-source duplicates if the operator supplies a reviewed production CSV.
Authenticated collection remains out of scope. Formal migrations, a scheduler or a persistence
change remain trigger-based decisions, not current requirements. The handover Definition of Done is
reconciled requirement-by-requirement in `docs/reports/mvp_definition_of_done_audit_v1.md` (18/18
PASS).

## 2026-09-02 product-direction update

The original deterministic-filtering MVP remains the current implemented runtime, but it is no longer the target product behavior.

Current accepted direction is documented in:

- `docs/decisions/0001-0011`;
- `data/target_employers/target_employers_v0_2.yaml`;
- `docs/ROADMAP_V2.md`.

Important operational warning: the current `scan-official` command still invokes the old deterministic `VacancyFilter` before canonical-job persistence. Do not treat a new run as the final cyber-pilot ingestion path until P0.2-P0.4 of `ROADMAP_V2.md` are implemented.
