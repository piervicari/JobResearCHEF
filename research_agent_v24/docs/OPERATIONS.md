# Operations runbook

## Operating model

The research agent is started manually and stores state in a local SQLite database. Offline commands
and live network scans are deliberately separate. Run commands from the repository root.

## Command impact

| Command | Network | Writes local state | Intended use |
|---|:---:|:---:|---|
| `research-agent` | No | No | Show command help. |
| `adapter-coverage` | No | No | Inspect routing before a scan. |
| `benchmark-taxonomy` | No | Reports | Verify deterministic filter quality. |
| `backup-db` | No | Backup file | Create and integrity-check an explicit SQLite backup. |
| `verify-recovery` | No | Restored copy, report | Prove a backup can be restored exactly. |
| `validate-master` | No | Reports | Validate authoritative import metrics. |
| `apply-registry-changes` | No | Database, master and reports | Apply reviewed versioned route changes. |
| `reclassify-current` | No | Database | Apply taxonomy changes to stored observations. |
| `init-db` / `import-master` | No | Database | Initialize local state. |
| `ingest-linkedin-csv` | No | Database | Import a reviewed, user-supplied public CSV. |
| `scan-official` | Yes | Database and cache | Fetch a bounded set of official portals. |

## First-time initialization

```bash
uv sync --dev
uv run research-agent init-db
uv run research-agent import-master
uv run research-agent validate-master
uv run pytest
uv run ruff check .
```

Do not proceed to a live scan if master validation or the offline suite fails.

## Versioned registry changes

Copy `data/import_templates/registry_changes.csv`, remove the example row and add one reviewed action
per cluster. `UPDATE` and `RETIRE` require the exact current jobs URL in `Old Jobs Search URL`; every
action requires evidence, verification date and reason. Apply it with explicit artifact paths:

```bash
uv run research-agent apply-registry-changes data/portal_resolution/registry_corrections.csv \
  --source-version registry-corrections-v1 \
  --master-output data/company_universe/master_company_universe_registry_corrections_v1.csv \
  --report docs/reports/registry_corrections_v1.md \
  --json-report docs/reports/registry_corrections_v1.json
```

The command is checksum-idempotent, preserves old portal rows and refuses to overwrite the exported
master. Use `SUSPEND` rather than `RETIRE` when the official mapping remains correct but automated
access is denied; use `RESUME` only with new reviewed evidence. Never edit master v1.5 in place.

## Pre-scan gate

Before every live cohort:

1. Confirm the selected Portal IDs and adapter routing with `adapter-coverage` and a database query or
   dashboard review.
2. Confirm there is sufficient free disk space for the database and response cache.
3. Keep the default automatic pre-scan SQLite backup enabled, or run `research-agent backup-db`
   explicitly and record its path and checksum.
4. Start with explicit Portal IDs. Use stable `--limit` only when the ordered selection has been
   inspected.
5. Record the cohort purpose, expected adapters, maximum acceptable failures, retries and empty
   complete snapshots.
6. Never use `--all` as an exploratory command.

`scan-official` creates an online, integrity-checked SQLite backup before network activity unless the
operator deliberately passes `--no-backup`. After fetch, the configured gate checks failure rate,
retry rate, HTTP `429` and complete empty snapshots. A failed gate retains scanner evidence but skips
vacancy processing and lifecycle advancement.

Backups are not pruned automatically. Inspect `data/backups/` and available disk space before each
rollout. Use `research-agent prune-backups --keep-last 3` for an exact dry-run and add `--apply` only
after reviewing every path. Always retain at least the backup associated with the current database
and any run under investigation.

Live scans use a stable identifiable User-Agent. `RESEARCH_AGENT_SCANNER__OPERATOR_CONTACT` is
optional metadata and may stay blank; if configured, it is appended to the User-Agent. Request
budgets and cooldowns are stored in the run configuration snapshot. See decision 0017.

The default hard limits are 30 requests per host and 500 requests for the complete run. A `401`,
`403`, `429`, robots denial or strong access-challenge signature opens the host circuit. The scanner
then persists a 24-hour cooldown for matching registry hosts. `--ignore-cooldowns` is an explicit
operator override intended only after the underlying route or access condition has been reviewed.

## Recommended rollout

Use the same stop conditions at every stage:

1. targeted probes for each newly supported adapter;
2. 25 portals;
3. 50 portals;
4. 100 portals;
5. full registry only after an explicit review of the preceding evidence.

Stop expansion if any of these occurs: unexpected routing growth, authentication/CAPTCHA response,
robots denial, repeated `429`, retry spike, schema drift, abnormal empty complete snapshots, memory or
disk growth, or lifecycle changes that cannot be explained from source evidence.

Default gate thresholds are configured in `config/settings.yaml`: at most 10% failed portals, at most
20% retries per request, zero `429` and zero complete empty snapshots.

The corrected 2026-08-31 representative 100-portal cohort passed at 8% failure, zero retries, zero
`429` and zero unexpected complete empty snapshots. This authorizes conservative manual operation,
not an unattended full-registry scan; see `docs/reports/scan_scale_validation_v1.md`.

## Conservative operating cadence

Treat these values as ceilings, not permission to override a site's stricter robots policy,
server-directed delay or terms:

1. Begin every network session with 5-10 reviewed canary portals and inspect the gate before
   continuing.
2. Run structured adapters in explicit reviewed cohorts of at most 50 portals, no more than twice per
   week. Run incomplete HTML fallback cohorts of at most 50 portals, no more than once per week.
3. Do not deliberately select the same host more than once in a calendar day. The stricter runtime
   ceilings of 30 requests per host and 500 per run still apply.
4. Never schedule or leave `--all` unattended. Expansion beyond a canary is a new operator decision,
   not an automatic continuation.
5. Stop the session on a failed gate, any `429`, authentication/CAPTCHA response, robots denial,
   challenge signature, unexpected complete empty snapshot or unexplained lifecycle change. Preserve
   the evidence, respect the persisted cooldown and remediate before another attempt.

This cadence reduces operational and access-blocking risk; it cannot guarantee that a third party
will continue to allow automated requests. A provider can always change its public contract or deny
access.

## Failure handling

- One portal failure is isolated; inspect its persisted attempt and do not immediately rerun a large
  cohort.
- `429` means reduce frequency and respect the requested delay. Do not rotate proxies or identities.
- A cooled host must not be retried merely to see whether the block disappeared. Resolve the route or
  wait for the cooldown; record the justification before using `--ignore-cooldowns`.
- `401`, `403`, CAPTCHA or login requirements are boundaries, not implementation challenges to
  bypass.
- A generic or otherwise incomplete snapshot may miss jobs but cannot close them.
- A structured empty snapshot must be reviewed before allowing a second successful absence to close
  prior jobs.

## Recovery

If a run produces suspect data, stop further scans, preserve the database and cache for diagnosis,
export the run and portal IDs, and restore the pre-run backup to a separate path. Do not delete the
suspect database until the discrepancy is understood. Reclassification can correct taxonomy output
without repeating network requests; it cannot repair a malformed source observation.

Verify a restore without overwriting either the working database or an existing destination:

```bash
uv run research-agent verify-recovery data/backups/backup.db \
  --destination /tmp/research-agent-restored.db \
  --report /tmp/recovery.md
```

The command requires the restored file to match the backup checksum exactly, pass SQLite
`integrity_check` and contain identical counts for every user table. Remove the temporary restored
copy only after reviewing the report.

## Browser fallback

Playwright is not part of the runtime scanner and is not a project dependency. ADR 0008 records why
the staged rollout did not justify it. Any future use requires a new ADR for named portals, a strict
allowlist, blocked downloads and nonessential resources, and destination/rate/resource budgets at
least as strict as the HTTP scanner.
