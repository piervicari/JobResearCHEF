# 0018 — Canary progression is one host at a time

Status: ACCEPTED
Date: 2026-09-02

## Decision

During the initial live-network validation, scan exactly one explicitly selected portal per live command. Do not run a multi-portal live canary until at least several heterogeneous single-host canaries have been reviewed.

Dry-run remains mandatory before the first live call to a new portal.

## Why

The objective of the canary is not throughput. It is to isolate failures and learn the request behavior of the scanner while minimizing impact on the user's residential IP and on the target site.

A single-host canary makes attribution trivial:

- which host received traffic;
- which adapter generated requests;
- how many requests were necessary;
- whether a 401/403/429/challenge was host-specific;
- whether the parser can produce useful jobs within the tiny request budget.

A clean result is evidence only for that host/access pattern at that time; it is not proof that other sites will tolerate the client.

## Current evidence

First live canary from the user's Mac/network:

- portal: 69 — KPMG Italy;
- adapter: `successfactors_rmk`;
- HTTP requests: 1;
- response: HTTP 200;
- retries: 0;
- jobs observed: 5;
- semantic processing: skipped;
- result: SUCCESS.

No blocking signal was observed in this test.

## Next progression

1. PayPal portal 514 (Workday), dry-run then live.
2. Mercedes-Benz portal 217 (Taleo-style), dry-run then live.
3. Review the three traces before increasing breadth.
4. If all are clean, test one previously unknown/lower-criticality portal with the same one-host policy.
5. Only then consider small sequential cohorts.

## Trade-off

This approach is slower than scanning three portals in one command, but the extra commands cost almost nothing and provide much clearer evidence. During initial validation, observability and containment are more valuable than speed.
