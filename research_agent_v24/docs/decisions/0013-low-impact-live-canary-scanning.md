# 0013 — Low-impact live canary scanning before core rollout

Status: **ACCEPTED + IMPLEMENTED**  
Date: 2026-09-02

## Context

Before scanning the full core employer set, we want evidence that official career portals/ATS endpoints tolerate the scanner without risking unnecessary rate limits, blocks, or disruption to ordinary manual browsing from the user's connection.

## Decision

Do not run a full/core scan yet.

Use a staged **canary cohort** of lower-criticality employers and an intentionally conservative network profile. Test the existing network/scanner layer on a disposable copy of the database so the old deterministic semantic filter cannot contaminate production data.

Do NOT use rotating proxies, IP rotation, randomized fingerprints, randomized user agents, CAPTCHA bypass, or other anti-detection behavior. The goal is low-impact, transparent access to official public job sources, not evasion.

### Canary network profile

Initial live profile:

```text
global_concurrency                    = 1
per_domain_concurrency                = 1
per_domain_min_interval_seconds       = 10
max_retries                           = 0
max_requests_per_host_per_run         = 3
max_requests_per_run                  = 9 (phase 1) / 15 (phase 2)
max_pages_per_portal                  = 1
max_jobs_per_portal                   = 25
host_cooldown_hours                   = 72
HTTP 429 tolerated by gate            = 0
```

No headless browser in canary phases.

Keep one stable user agent. Operator contact is supplied through environment configuration, never committed to the repository.

Reuse the existing conditional HTTP cache (`ETag` / `Last-Modified` -> `If-None-Match` / `If-Modified-Since`) on recurring production scans. This reduces transferred data and server work when providers support HTTP validators. For the first canary, use a dedicated canary cache so the test actually exercises current network access without modifying production cache state.

### Automatic stop conditions

Stop expansion immediately on any of:

- HTTP 429;
- HTTP 403/challenge/block indication;
- robots disallow;
- unexpected redirect to anti-bot/challenge page;
- repeated 5xx attributable to the access pattern;
- parser behavior that would require aggressive pagination;
- request-budget exhaustion.

Do not retry a blocked host during the same test. Respect cooldowns.

### Staged cohort

Phase 0: fixtures/offline tests only.

Phase 1: 3 previously healthy, non-critical canaries on different stacks/hosts:

- KPMG — portal 69 — SuccessFactors-style;
- PayPal — portal 514 — Workday;
- Mercedes-Benz — portal 217 — Taleo-style.

Phase 2, only if Phase 1 is clean: 3–5 currently `UNKNOWN` lower-risk canaries, diversified by backend, for example:

- Audi — portal 237 — SuccessFactors-style;
- Honeywell — portal 158 — Oracle Recruiting Cloud;
- Armis — portal 301 — SmartRecruiters signal;
- Shell — portal 273 — Workday;
- Rapid7 — portal 89 — Phenom-style.

The exact cohort is operational and may change; the policy does not.

### Database isolation

Every canary live run operates on a timestamped disposable copy of `data/research_agent.db` under `data/canary/`.

This is required until the new LLM-first semantic persistence path replaces the existing `VacancyFilter` processing path.

## IP / fingerprint model

With HTTP/API adapters and no browser, there is no browser canvas/font fingerprint surface. Servers can still observe IP address, headers, TLS/client characteristics, timing, and request patterns.

The safest first-line mitigation is therefore *less traffic and stable behavior*, not attempts to disguise identity.

For long-running automation, consider a dedicated fixed egress environment later so automated traffic is operationally separated from the user's normal residential browsing. Do not use rotating infrastructure as an evasion mechanism.

## Promotion rule

Only increase cohort size or request budgets after reviewing the previous phase's request counts, statuses, retries, warnings, and portal health changes.


## Implementation note — 2026-09-02

The CLI now provides:

- `prepare-canary-db` — integrity-checked disposable SQLite copy;
- `scan-canary --dry-run` — prints exact targets and hard budgets with zero network requests;
- `scan-canary` — scans 1–3 explicit portals sequentially, with concurrency 1, max 3 requests/portal, max one page, zero retries, 72h block cooldown, 10s pause between portals and automatic stop on 401/403/429/challenge/robots signals;
- canary scanning is network-only and never invokes deterministic semantic processing or the future LLM.

The command refuses the configured production DB.
