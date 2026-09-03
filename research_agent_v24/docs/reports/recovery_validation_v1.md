# SQLite recovery validation

Validated: 2026-08-31T22:30:40+02:00. The restored copy was intentionally created outside the
repository and removed after this report and the exact comparisons below were reviewed. The retained
backup is unchanged.

- Backup: `/Users/pierfrancescovicari/Documents/research_agent/data/backups/research_agent_20260831T203030.428198Z.db`
- Restored copy: `/private/tmp/research_agent_final_recovery_20260831.db`
- SHA-256: `2a7f58cc8bdd030fc25f76803c4eb92886b173b26699c3bcfca24ffd5731c285`
- Integrity check: `ok`
- Exact checksum match: `True`

## Table counts

| Table | Rows |
|---|---:|
| `canonical_jobs` | 108 |
| `cluster_portal_mappings` | 589 |
| `company_aliases` | 6 |
| `company_records` | 12,503 |
| `corporate_clusters` | 11,798 |
| `import_batches` | 7 |
| `job_observations` | 14,320 |
| `portal_scan_attempts` | 415 |
| `portals` | 534 |
| `registry_change_audit` | 58 |
| `scan_runs` | 29 |
| `source_jobs` | 5,789 |
