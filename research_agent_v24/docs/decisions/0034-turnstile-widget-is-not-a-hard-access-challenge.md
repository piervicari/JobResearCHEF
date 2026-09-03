# 0034 — Embedded Turnstile widget is not a hard access challenge

- **Date:** 2026-09-02
- **Status:** ACCEPTED + IMPLEMENTED

## Context

The first selective detail follow-up fetched Wazuh `robots.txt` and the Threat Intelligence detail page with HTTP 200, but `HttpFetcher` raised `AccessChallengeError` because the HTML contained `cf-turnstile`. The public vacancy content is in fact accessible; Wazuh embeds Cloudflare Turnstile around the application form.

The same run then opened the host circuit and skipped the next Wazuh detail candidate.

## Decision

Do **not** treat the mere presence of `cf-turnstile` in an otherwise normal 200 HTML response as a blocking challenge.

Keep strong challenge signals blocking, including:

- Cloudflare `Just a moment...` interstitials;
- `cf-chl-*` challenge markup;
- explicit `verify you are human` pages;
- PerimeterX/Radware/PerfDrive challenge endpoints;
- HTTP 401/403/429 circuit-breaker statuses.

## Why

A security widget embedded in an application form is not equivalent to the vacancy page itself being inaccessible. Treating both cases identically creates false access failures and unnecessarily opens the per-host circuit.

## Implementation

`HttpFetcher._CHALLENGE_MARKERS` no longer includes `cf-turnstile` as a hard marker. Regression tests cover both:

1. a normal job page containing an embedded Turnstile widget — allowed;
2. a genuine Cloudflare challenge/interstitial — still blocked.

## Trade-off

A future challenge page that contains only a bare Turnstile marker and none of the stronger signals could pass this heuristic. If observed empirically, improve the detector using page-level challenge structure rather than reverting to the overly broad substring rule.
