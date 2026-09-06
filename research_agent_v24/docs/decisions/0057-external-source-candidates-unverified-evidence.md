# Decision 0057: External registries are unverified source candidates with provenance

- Status: ACCEPTED
- Date: 2026-09-06

## Decision

External job-source registries (first: `ats-scrapers` @
`6b44a1badc9bfbf5cf176f75265cc5729e520e99`, MIT with attribution) are imported
only as unverified source candidates with full provenance, into the dedicated
`external_source_candidates` table. A candidate is evidence, never a source:
every row stays `verified=false, verified_at=null`, and nothing in the scan
path (AdapterRegistry, Scanner, bindings) reads this table.

## Why

The offline overlap (V2, canonical universe v1_12, 12,503 companies) matched
562 companies to 851 HIGH_CONFIDENCE board candidates. That knowledge is worth
keeping — it lets future scans skip discovery for those companies — but only
if it can never silently become an authoritative portal. A separate table with
a fail-closed default, plus a guardrail that rejects non-HIGH rows, gives us
the knowledge with zero promotion risk.

## Rules (locked)

- HIGH_CONFIDENCE rows only; anything else is skipped and reported.
- No automatic bindings: importer never touches `bindings.json`, `portals`,
  `cluster_portal_mappings`, scan queues, or the scheduler.
- Multiple candidates per company preserved; no winner-picking.
- Deterministic identity (company, provider, ATS, normalized URL, slug);
  repeat imports insert zero duplicates.
- Unsupported ATS (bamboohr, teamtailor, workable, …) preserved as knowledge
  with a `support_class` label; import behavior identical.
- Importer is offline: no HTTP client imports (`urllib.parse` for URL
  normalization only).
- Future validation is lazy and out of scope: on scan need → inspect HIGH
  candidates for that one company → single sequential one-time validation →
  confirmed candidates enter through the normal audited registry path
  (RegistryChangeAudit), rejected ones are marked without traffic. Policy for
  that future step: on demand, one company at a time, sequential, no bulk, no
  concurrency, cache permanently, stop immediately on 403/429/challenge, no
  brute-force, no slug enumeration, no UA/proxy rotation.

## Implementation shape

```text
ats_scrapers_high_confidence.csv (offline, frozen)
  -> research_agent/company/external_candidates.py (import_external_candidates, --dry-run)
  -> external_source_candidates (UNIQUE identity, verified=false)
  -/-> portals / mappings / bindings / scan_runs (untouched; anti-cheat tested)
```

No migration file: `create_schema` (`create_all`) creates the table on new and
existing SQLite DBs. No service, queue, registry, scheduler, or dependency.

## Trade-offs / challenges

- New table instead of reusing `Portal`/`CompanyAlias`: deliberate. Reusing
  `portals` would make candidates scannable; reusing aliases would overload
  verified-name semantics. One small table keeps verified/unverified states
  unconfusable.
- `internal_company_id` is a plain string, not a FK to `company_records`, so
  candidates import into empty/test DBs without requiring the master import.

## Current implementation impact

- `db/models.py`: +`ExternalSourceCandidate` (~48 LOC).
- `company/external_candidates.py`: importer + dry-run (~270 LOC, stdlib + sqlalchemy).
- `cli.py`: `import-external-candidates` command (~26 LOC).
- `tests/test_external_candidates.py`: 9 tests.
- Attribution/provenance stored per row (provider + commit); MIT attribution
  obligation for ats-scrapers data honored structurally.

## Open questions

- Rejection/stale marking of disproven candidates (needs the future validation step).
- Expiry policy for candidate evidence if upstream registries drift.
