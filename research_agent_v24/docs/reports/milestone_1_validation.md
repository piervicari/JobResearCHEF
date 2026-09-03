# Milestone 1 - Master v1.5 validation

**Overall result:** PASS

- Generated at (UTC): 2026-08-31T20:20:58.384944+00:00
- Authoritative source: `/Users/pierfrancescovicari/Documents/research_agent/data/company_universe/master_company_universe_v1_5_portal_resolution_wave5.csv`
- Source SHA-256: `bae44ad9ab0a5800bec884b43fc236506d9da3ea51f72477830e5023fa81e7df`
- Source checksum matches import evidence: `yes`
- Import batch ID: `1`

## Acceptance checks

| Metric | Expected | Actual | Result |
|---|---:|---:|:---:|
| `master_rows` | 12,503 | 12,503 | PASS |
| `unique_record_ids` | 12,503 | 12,503 | PASS |
| `corporate_clusters` | 11,798 | 11,798 | PASS |
| `resolved_rows` | 1,263 | 1,263 | PASS |
| `resolved_clusters` | 575 | 575 | PASS |
| `unique_resolved_jobs_urls` | 510 | 510 | PASS |

## Authoritative import snapshot

- Cluster-to-portal mappings: 575
- Deduplicated operational portals: 510
- Portals with cluster-specific ATS metadata variants: 6
- URL normalization preserves paths and query strings and removes only safe syntax noise.
- Company-specific portal metadata remains on the cluster-to-portal mapping.
- Later versioned corrections may change current resolved/portal counts without mutating this historical acceptance snapshot.

## Current synchronized state

- Resolved rows: 1,277
- Resolved clusters: 589
- Active registry portals: 524

## Gate

All Milestone 1 acceptance criteria passed. Scanner implementation may proceed; full-registry scanning remains a separate explicit opt-in and is not validated by this report.
