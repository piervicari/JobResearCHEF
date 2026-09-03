# Live canary test plan

Updated: 2026-09-02

Purpose: validate only the network/access layer before any core-employer rollout.

See decisions `0012`, `0013`, and `0014`.

## Important limitation

A canary must be run from the machine/network whose IP behavior we want to evaluate. A scan executed in ChatGPT infrastructure would test ChatGPT's egress, not the user's residential IP, so it is not a substitute.

## 0. Optional operator contact

No shell `export` is required. If you want an operator contact in the scanner User-Agent, copy `.env.example` to `.env` and set `RESEARCH_AGENT_SCANNER__OPERATOR_CONTACT` there. The canary can also run with this field blank. Never commit the local `.env`.

## 1. Create a disposable DB safely

Do not use `cp` on a possibly live SQLite/WAL database. Use the online SQLite backup command:

```bash
research-agent prepare-canary-db --replace
```

This creates:

```text
data/canary/research_agent_canary.db
```

and verifies SQLite integrity.

## 2. Phase 1 — one host at a time

Known-good, lower-criticality diverse portals:

- KPMG — 69 — SuccessFactors RMK
- PayPal — 514 — Workday
- Mercedes-Benz — 217 — Taleo-style

For each new host, run a dry-run first and then, only if the host/URL is correct, a live command for that single portal.

Example for PayPal:

```bash
research-agent scan-canary --portal-id 514 --dry-run
research-agent scan-canary --portal-id 514
```

Do not combine the three into one live command during initial validation.

## 3. Phase 1 live canary evidence

KPMG portal 69 was tested on 2026-09-02 and passed with one HTTP 200 request, zero retries, and five observed jobs. See `CANARY_RESULTS_2026-09-02.md`.

The safety profile is hardcoded by the canary command rather than relying on environment overrides:

```text
portals                              <= 3
portals scanned sequentially         yes
global concurrency                   1
per-domain concurrency               1
minimum same-host interval           10s
pause between selected portals       10s
retries                              0
max requests per portal/run          3
max pages per portal                 1
max jobs returned per portal         25
block cooldown                       72h
semantic processing                  disabled
production database                  rejected
```

Worst-case phase-1 request budget is 9 HTTP attempts across three explicit portals.

### Automatic stop

The command stops before moving to the next selected portal on:

- 401;
- 403;
- 429;
- access challenge detection;
- robots disallow.

Do not immediately retry a host after such a signal.

## 4. Review before Phase 2

Record:

- total requests;
- HTTP statuses;
- adapter selected;
- jobs observed within the one-page cap;
- retries (must remain zero);
- 403/429/challenge/robots signals;
- redirects/warnings;
- whether a provider requires more than the deliberately tiny canary budget.

A clean canary proves only that this access pattern was tolerated at that moment. It does not guarantee other sites will behave identically.

## 5. Phase 2

Only after reviewing Phase 1. Start with three, not all five:

- Audi — 237
- Honeywell — 158
- Armis — 301
- Shell — 273
- Rapid7 — 89

Run a dry-run first and retain the same hard safety profile.

## What canary does NOT validate

- full pagination;
- complete job inventory;
- LLM classification;
- semantic accuracy;
- production cadence;
- browser/headless fallback;
- whether an unrelated high-value portal will tolerate the same client.
