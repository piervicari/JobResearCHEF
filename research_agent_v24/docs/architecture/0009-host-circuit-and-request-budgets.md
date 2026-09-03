# ADR 0009: Host circuit breakers, persistent cooldowns and hard request budgets

- Status: Accepted
- Date: 2026-08-31

## Context

Per-domain concurrency and start intervals limit request rate but do not cap total pagination. A
single adapter could therefore make many sequential requests, and a later cohort could immediately
retry a host that had returned an access-control response in the preceding run.

## Decision

- Limit each run to 1,000 network requests and each host to 100 by default.
- Count redirects and retries because each is a real network request.
- Open an in-memory host circuit on `401`, `403`, `429` and strong human-verification signatures.
- Stop retrying immediately on the first `429`; the cohort gate already treats any `429` as a stop
  condition.
- Persist a 24-hour cooldown on matching registry hosts after access denial, challenge or robots
  denial.
- Require an explicit `--ignore-cooldowns` override to retry a cooled host.
- Originally required a locally configured operator contact before CLI live scans and included it
  in the identifiable User-Agent. **Superseded by product decision 0017:** the User-Agent remains
  stable/identifiable, but operator contact is optional metadata.

## Consequences

Large or unexpectedly paginated boards can become incomplete when they exhaust a budget, which is
safer than continuing unbounded traffic. A host shared by several portals may cause the remaining
portals to fail closed after the first access signal. Cooldowns are operational protection, not proof
that access will become permissible later; denied routes still require review or retirement.
