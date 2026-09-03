# Security policy

## Supported scope

The project is an early local-first MVP intended for one trusted operator. It is not currently
designed as a hosted multi-user service or for accepting arbitrary public URLs.

Security fixes apply to the current main working tree. There is no stable release-support matrix yet.

## Reporting a vulnerability

Do not include credentials, private vacancy data, browser profiles or exploit payloads in a public
issue. Report the affected component, reproduction conditions, impact and the smallest safe proof of
concept directly to the repository owner. Rotate any credential that may have been exposed before
sharing logs.

## Trust boundaries

- The authoritative company master and manually supplied import files are trusted operator inputs,
  but still require schema validation.
- Portal URLs, redirects, DNS results, HTTP headers and response bodies are untrusted network input.
- SQLite and `data/cache/http` contain local operational state. Public vacancy content may still
  include names or contact details and should not be published automatically.
- The dashboard is intended for localhost use. Exposing it to a network requires authentication,
  authorization and deployment hardening not provided by this repository.
- Browser automation is outside the accepted runtime boundary; if reconsidered, it is a separate
  higher-risk trust boundary because it executes remote JavaScript.

## Required controls

- Allow only HTTP(S) public destinations and revalidate every redirect target.
- Reject loopback, private, link-local, multicast, reserved and otherwise non-public IP addresses.
- Bound concurrency, request duration, total run duration, retries, response size and server-directed
  delay.
- Enforce per-host and per-run request budgets. Open a host circuit on `401`, `403`, `429` or a
  strongly detected access challenge, and persist a cooldown across runs.
- Use an identifiable user agent and never bypass access controls, CAPTCHA or rate limits.
- Do not introduce browser execution without the allowlist, isolation and budgets required by ADR
  0008 and a new accepting ADR.
- Keep cache headers allowlisted; never persist authentication or session headers.
- Back up the SQLite database before a live cohort that can advance lifecycle state.

## Known limitations

The hardened fetcher validates public DNS before each request and redirect, but the underlying client
resolves again when connecting; it does not cryptographically pin the validated address. Registry
inputs must therefore remain curated rather than accepting arbitrary user URLs. Current HTTP parsers
do not execute page JavaScript. Playwright is not a project dependency and ADR 0008 excludes browser
automation from the runtime scanner.
Automated backups support only file-backed SQLite.

The generic HTML fallback enforces `robots.txt`. Structured ATS adapters use named, observed public
contracts; their continued public availability and provider terms remain external dependencies. A
successful response is not permanent permission, so access-control signals always fail closed.

Operational mitigations and recovery steps are documented in
[`docs/OPERATIONS.md`](docs/OPERATIONS.md).
