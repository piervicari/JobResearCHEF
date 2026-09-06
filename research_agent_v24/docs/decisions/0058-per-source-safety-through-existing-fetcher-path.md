# Decision 0058: Source-specific conservative network policies through the existing Scanner/HttpFetcher path

- Status: ACCEPTED
- Date: 2026-09-06

## Decision

SourceSpec safety requirements are enforced per source through small generic
extensions of the existing networking path — no separate declarative stack,
no second retry/pacing/circuit-breaker engine, no scheduler, no new
dependencies:

- per-request interval FLOOR (`min_seconds_between_requests`) and retry
  CEILING (`max_retries_on_5xx`) travel on `FetchRequest`; the fetcher
  applies `max(global, floor)` / `min(global, ceiling)`;
- per-scan wire-attempt budget (`max_requests_per_run`), periodic long pause
  (`long_pause_every_n_requests`/`long_pause_seconds`) and the
  consecutive-failure budget (`max_consecutive_errors`) live on
  `PortalScanContext` (one instance per scan); the adapter only wires spec
  values, retries the same offset on ordinary failures, and stops with
  partial results otherwise.

## Why

Three spec fields (`long_pause_*`, `max_consecutive_errors`) had no runtime
mechanism, so no declarative source was honestly live-runnable; two more
(interval, retries) could only be satisfied by tightening globals for every
source. Per-source floors/ceilings/budgets fix all five without touching
global defaults or weakening any spec.

## Semantics (locked)

- `max_requests_per_run` counts WIRE attempts (retries/redirects included);
  overshoot past the last admitted fetch is bounded by that fetch's retries.
- Long pauses count LOGICAL fetch() calls: pause S before request N+1,
  2N+1, … — never after the final request. Retries do not shift pauses.
- Consecutive errors count failed LOGICAL fetches after normal fetcher
  retries; success resets; at threshold the scan stops (partial kept,
  `complete_snapshot=false`, explicit warning). Same-offset retry is
  termination-guaranteed by the threshold.
- 403/429/challenge bypass every budget and abort with zero further
  requests: 429/challenge propagate (FAILED isolation, host blocked by the
  fetcher); any non-2xx via `require_success` stops with partial kept and
  `complete_snapshot=false` (host block still recorded by the fetcher and
  the scanner's block_reasons via `final_http_status`).
- Any safety stop (budget, consecutive, HTTP error) forces
  `is_complete_snapshot=false`, so the lifecycle can never close jobs on a
  truncated run. Specs are never weakened; the runtime adapts to them.
- Preflight: `sequential_only` is the only requirement still validated
  against globals (shared concurrency cannot be overridden per-request).
  All other fields are ENFORCED per-request/per-scan, so defaults yield
  SAFE_TO_RUN — honestly, because the runtime provably applies the
  stricter of spec/global. No bypass flag exists.

## Implementation shape

```text
spec["safety"] -> adapter.scan wiring only ->
  FetchRequest(min_interval_seconds, max_retries) -> HttpFetcher/DomainRateLimiter
  configure_scan_limits(...) -> PortalScanContext.fetch funnel
```

4 production modules lightly extended (`pipeline/http.py`,
`sources/base.py`, `sources/declarative/adapter.py`,
`sources/declarative/safety.py`); `config.py`, `scanner.py`, specs, and
operational config untouched.

## Trade-offs / challenges

- Full Mercedes catalog (57 requests, one host) still exceeds the default
  global per-host budget (30): the scan stops partial and incomplete rather
  than loosening globals per-source. Full-catalog config (operator choice,
  NOT applied): `max_requests_per_host_per_run >= ~60`; interval/retries may
  stay at defaults (floors/ceilings apply per-request). NVIDIA/Microsoft
  need host budget sized to their catalog (10/page + probe).
- Non-2xx other than 429 stops at first occurrence instead of burning the
  consecutive budget: persistent HTTP errors are not worth retrying.

## Current implementation impact

- No new HTTP client, scheduler, retry/pacing/circuit-breaker engine.
- Adapter holds no safety state beyond wiring values and the same-offset
  retry loop; counters live in the context (per-scan by construction).

## Open questions

- None for this step. Lazy validation of external candidates remains future
  work under the policy in ADR-0057.
