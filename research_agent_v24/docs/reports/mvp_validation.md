# MVP implementation validation

Generated: 2026-08-30 (Europe/Rome workspace)

## Result

The handover Definition of Done is implemented for a bounded, local-first MVP. Milestone 1 remains
an exact PASS after scanner and vacancy data were added to the same database.

## Authoritative master gate

| Metric | Expected | Actual | Result |
|---|---:|---:|:---:|
| Master rows | 12,503 | 12,503 | PASS |
| Unique Record ID | 12,503 | 12,503 | PASS |
| Corporate Cluster ID | 11,798 | 11,798 | PASS |
| Resolved master rows | 1,263 | 1,263 | PASS |
| Clusters with portal resolution | 575 | 575 | PASS |
| Unique Resolved Jobs Search URL | about 510 | 510 | PASS |

Source SHA-256: `bae44ad9ab0a5800bec884b43fc236506d9da3ea51f72477830e5023fa81e7df`.
The detailed machine-readable result is in `milestone_1_validation.json`.

## Automated verification

- `uv run ruff check .`: PASS.
- `uv run pytest -q`: 99 passed.
- Streamlit AppTest: zero exceptions.
- Local dashboard smoke: health endpoint and root page returned HTTP 200.

Tests cover authoritative import, Wave 5 asset coherence, portal deduplication, URL normalization,
data-model constraints, four structured ATS contracts, generic HTML/robots behavior, concurrency,
rate interval, retry/429/cache behavior, scan failure isolation, filters, deduplication, lifecycle,
incomplete-snapshot safety, reclassification and LinkedIn manual import.

## Bounded live scanner evidence

No full-registry or per-master-row scan was performed.

| Run | Purpose | Portals | Success | Requests | Retries | Raw jobs |
|---:|---|---:|---:|---:|---:|---:|
| 3 | Structured ATS cohort | 15 | 15 | 15 | 0 | 452 |
| 4 | Conditional-cache rerun | 15 | 15 | 15 | 0 | 452 |
| 5 | Taxonomy correction | 12 source/adapter groups | 12 | 0 | 0 | 452 |
| 6 | Audited taxonomy reclassification | 12 source/adapter groups | 12 | 0 | 0 | 452 |

The 15 live portals comprise 11 Greenhouse, 2 Lever, 1 Ashby and 1 SmartRecruiters portal. Run 4
used cached bodies after validation. Runs 5-6 made no network requests. The latest run stored the
complete parsed taxonomy in its audit snapshot and produced 436 `EXCLUDE`, 16 `REVIEW` and 0
`INCLUDE` decisions. Zero `INCLUDE` is a truthful result for this limited snapshot, not a
relaxed-filter failure: the 16 ambiguous cyber vacancies lack an explicit junior/intern marker and
remain available for review.

## Current persisted state

- 452 active source jobs, including excluded jobs retained for audit and future reclassification.
- 73 historical canonical jobs; 16 are active and all are `REVIEW`.
- 15 `HEALTHY` structured portals and 495 unscanned `UNKNOWN` portals.
- 510 active registry portals: 15 verified structured routes and 495 generic fallback routes.
- No production LinkedIn file has been imported; the compliant import path is covered by tests.

## Definition of Done trace

All 18 handover items have an implemented MVP path: exact master import; cluster and portal dedup;
manual start; bounded official scans; real ATS adapters; rate limiting/backoff; normalization;
cyber/seniority/geography filtering; source and cross-source dedup; history; active/closed lifecycle;
run metrics; dashboard; no required LinkedIn scraper; critical tests; and per-portal failure isolation.

The qualification is important: the current live evidence is a significant structured sample, not
complete coverage of all 510 portals. Expansion must remain bounded and adapter-evidence-driven.
