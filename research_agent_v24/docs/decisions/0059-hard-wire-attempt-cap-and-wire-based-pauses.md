# Decision 0059: Hard wire-attempt cap and wire-based pauses with zero overshoot

- Status: ACCEPTED
- Date: 2026-09-06

## Decision

1. `max_requests_per_run` is a HARD cap on actual outbound HTTP wire
   attempts for one source scan (initial requests, retries, redirect
   follow-ups). Wire attempt N+1 is structurally impossible: overshoot is 0.
2. Retries and redirects consume the budget.
3. Periodic long pauses are wire-based: pause S before outbound attempt
   N+1, 2N+1, … Retries and redirects shift pauses; never after the final
   attempt.
4. Cache conditional requests that touch the network count as wire
   attempts. There is no zero-wire cache path in the fetcher (verified:
   no early return; 304 still performs one outbound attempt).
5. Any budget exhaustion (per-scan cap, consecutive budget, global/per-host
   fetcher budget) is TERMINAL for the source scan: no same-offset retry,
   partial jobs kept, `is_complete_snapshot=false`, explicit warning.
6. No duplicate network stack: one `ScanWirePolicy` object per scan,
   mutated only by `HttpFetcher._guarded_request` (the single choke point
   every initial/retry/redirect attempt passes through exactly once).
7. Global/per-host fetcher budgets remain an independent, stricter ceiling;
   they are never loosened per-source.

## Why

The previous per-scan budget was checked before each logical fetch while a
single `fetch()` could emit several wire attempts (overshoot possible);
pauses counted logical fetches despite the `requests` name; and fetcher
budget exhaustion was retried as an ordinary failure. All three are now
exact, with 403/429/challenge precedence unchanged (stronger than any
budget) and legacy requests without policy on a byte-identical path.

## Ownership and lifecycle (§12)

- Enforcement source of truth: `ScanWirePolicy.used_wire_attempts`,
  mutated ONLY in `HttpFetcher._guarded_request` (cap check → pause →
  global budgets → exactly one `_request_once`, counted in `finally`).
- `PortalScanContext` builds one policy per scan via
  `configure_scan_limits`, attaches it to outgoing requests, pre-checks
  exhaustion (zero-fetch stop), and keeps a post-hoc `_wire_attempts`
  observation that can never exceed the cap.
- Policy objects are per-scan and not thread-safe by design
  (`sequential_only`); the fetcher stays shared.

## Trade-offs

- A redirect blocked by the cap surfaces as `RequestBudgetExceededError`
  (conservative stop), not as a redirect error — correct, since following
  it would exceed the declared tolerance.
- Transport-layer failures count as wire attempts (bytes moved or
  attempted): conservative direction for a cap.

## Current implementation impact

- `pipeline/http.py`: `ScanWirePolicy` + `FetchRequest.wire_policy` +
  choke-point enforcement (~+70 LOC).
- `sources/base.py`: policy construction/attachment, terminal pre-check;
  logical-pause block removed (~net -10 LOC).
- `sources/declarative/adapter.py`: `RequestBudgetExceededError` terminal
  (+~8 LOC). `safety.py`: doc semantics only.
- No config, schema, spec, migration, dependency, or operational-setting
  change. Full Mercedes reconciliation needs
  `max_requests_per_host_per_run >= ~60` (operator decision, NOT applied);
  spec budget 600 has ample margin over ~56-57 best-case wires.

## Open questions

- None for this step.
