# ADR 0008: No browser automation in the runtime scanner

- Status: Accepted
- Date: 2026-08-31

## Context

Playwright can drive a real browser engine and execute client-side JavaScript. It was listed as an
optional dependency, but no scanner code used it. The staged rollout exposed stale DNS and URLs,
explicit `robots.txt` denials, HTTP 403 responses and anti-bot challenges. Those conditions are not
evidence that JavaScript rendering is required; using a browser against them would add resource,
supply-chain and compliance risk without fixing the underlying coverage problem.

The structured adapters implemented so far obtain public data through documented or observable
HTTP contracts, server-rendered HTML and embedded bootstrap data.

## Decision

- Do not add a Playwright/browser fallback to the runtime scanner.
- Remove the unused optional dependency and browser-concurrency setting.
- Do not automate login, CAPTCHA, Cloudflare challenges or other anti-bot controls.
- Keep JavaScript-only portals as explicit coverage gaps unless a named portal demonstrates that
  rendering is necessary and permitted after ordinary HTTP/API investigation.
- Any future browser integration requires a new ADR, portal allowlist, separate concurrency and
  resource budgets, destination validation, download blocking and fixture-backed tests.

## Consequences

The default and optional installation surfaces are smaller, and scan behavior remains reproducible
at the HTTP boundary. Some portals will remain uncollected until their public contract is resolved or
the registry URL is corrected. A future browser worker remains possible, but it cannot be introduced
as a generic response to access denial.
