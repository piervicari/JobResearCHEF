# V2 safe quickstart

This sequence deliberately separates zero-network checks, the low-impact network canary, and LLM tests.

## 0. One-time local configuration

No shell `export` is required for normal use.

```bash
cp .env.example .env
```

For dry-runs and the network canary you do not need API keys. Before the first live LLM test, edit `.env` and add:

```text
GEMINI_API_KEY=...
OPENROUTER_API_KEY=...
```

`RESEARCH_AGENT_SCANNER__OPERATOR_CONTACT` is optional and may stay blank. Downloaded ZIP files are backups/versioned project copies; environment variables are unrelated to backup handling.

## A. Fresh V7 baseline: verify the AI queue — zero external requests

The distributed V7 database is already converted offline to the V2 payload/company format. Verify it:

```bash
uv run research-agent analyze-pending --limit 10 --batch-size 5 --dry-run
```

Expected preflight signal:

```text
missing_company: 0
```

If using an older database instead, migrate it offline first:

```bash
uv run research-agent prepare-v2-source-jobs --dry-run
uv run research-agent prepare-v2-source-jobs
```

## B. Prepare and preview the canary — zero network requests in dry-run

```bash
uv run research-agent prepare-canary-db --replace
uv run research-agent scan-canary --portal-id 69 --dry-run
```

For the very first live test, start with **one** known-good portal, not three.

Expected target:

```text
portal_id=69 host=careers.kpmg.it
```

Only after reviewing the dry-run should the `--dry-run` flag be removed.

## C. First live network canary — one portal only

```bash
uv run research-agent scan-canary --portal-id 69
```

Hard bounds remain: concurrency 1, retries 0, at most 3 requests, one page, 25 jobs, and stop on access/block signals. Semantic processing is skipped.

## D. First live LLM test — only after `.env` keys are configured

Start smaller than production:

```bash
uv run research-agent analyze-pending --limit 5 --batch-size 5
```

This does **not** access career sites. It operates only on locally queued jobs and uses the configured fallback routing.

## E. Later: small V2 discovery cohort

Only after a clean canary:

```bash
uv run research-agent scan-discover --portal-id <ID>
```

Unlike legacy `scan-official`, this stores source truth as `PENDING_AI` and does not use deterministic semantic filtering.

## Legacy warning

For V2 product testing, do not use `scan-official` or `reclassify-current`; those commands remain only for historical compatibility until removed/superseded after V2 validation.

## P0 end-to-end pilot (V14)

One-time secrets bootstrap (future ZIPs reuse the same file automatically):

```bash
uv run research-agent bootstrap-secrets
```

This searches useful `.env` files in sibling `research_agent*` extractions and installs the newest
one to `~/.config/research-agent/.env` without printing API keys. If the persistent file is already
configured, the command is a no-op.

The distributed project also contains a project-local `.env` file, but intentionally no live keys.

Run the controlled P0 pilot and create a shareable report:

```bash
./scripts/run_p0_pilot.sh
```

Default cohort: Detectify, Trellix, Horizon3.ai, Safe Security, Wazuh. The script resets a clean pilot
DB, performs a zero-network dry-run, scans each portal sequentially with <=3 requests and zero
retries, analyzes up to 50 new jobs in small batches, prints CYBER results in full, and writes the
complete terminal transcript to `output/test_runs/p0_end_to_end_pilot_*.log`.

The production DB is never used by `scan-pilot`.
