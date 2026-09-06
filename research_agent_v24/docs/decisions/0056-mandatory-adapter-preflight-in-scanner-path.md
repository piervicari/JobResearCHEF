# 0056 — Mandatory optional-adapter-preflight in the normal Scanner path

**Status:** ACCEPTED
**Date:** 2026-09-06
**Follows:** 0055 (hardening), 0054 (sibling adapter)

## Decision

**Optional adapter preflight hooks are mandatory when present in the
normal Scanner path.** `scan_portals._scan_one` invokes
`getattr(adapter, "preflight", None)` after `select()` and before
anything that could touch the network. Contract: return None when
safe, raise when unsafe; a non-None return is itself a
`PreflightContractViolation` failure (a verdict object can never be
silently ignored). Any hook failure yields a FAILED portal scan with
zero jobs, zero fetch attempts, `complete_snapshot=false`,
`final_http_status=None` — never UNSUPPORTED (the adapter exists; the
safety configuration forbids the scan). `DeclarativeSourceAdapter.preflight`
now implements this contract (ScannerSettings in → None out or
`UnsafeToRunError`), replacing its earlier verdict-returning draft;
verdict diagnostics remain available via `safety.preflight_safety`.

## Rationale

The hardening review proved `preflight()` existed but `scan()` never
called it and the scanner never invoked it: every declarative safety
requirement was decorative on the live path. Forgetting to call a
safety gate must be structurally impossible, not a harness convention.

## Previous gap

Explicit bindings won routing (0055) but an operator could still reach
the network with spec requirements (long pauses, consecutive-error
budget, retry/interval/request budgets) silently unenforced.

## Fail-closed behavior

Preflight runs after select, before context creation/scan; any
exception (including contract violations) short-circuits to FAILED
with the exception type preserved (`UnsafeToRunError` for safety
vetoes). No bypass flag, env var, or force parameter was added —
anywhere. The only way to scan is to satisfy the spec.

## Scanner remains generic

Zero source/platform/vendor tokens in the hook path (tested, modulo
one pre-existing Greenhouse/Ashby example comment that predates it);
no `isinstance`, no name checks; no `FetchRequest`/`SourceSpec`
knowledge. The hook convention is documented as a comment on the
`SourceAdapter` Protocol, deliberately NOT added to it.

## Legacy adapters without hook unaffected

`getattr(..., None)` + `callable()` check: adapters without
`preflight` scan exactly as before (proven by a real legacy
end-to-end scan plus the untouched full suite). No wrapper, no
protocol change, no new DB status.

## Unsupported active SourceSpec safety requirements block before network

Verified live-offline via `scan_portals` + exploding MockTransport:
Mercedes (long pauses, consecutive-error budget) → FAILED/
`UnsafeToRunError`/zero calls. A too-permissive configuration
(`max_retries=2` vs spec max 1) → `SCANNER_SETTINGS_TOO_PERMISSIVE`,
same zero-network outcome. A compatible synthetic spec →
`test_safe_preflight_runs_normal_scan` guards against blocking
everything indiscriminately. Honest current state (§11): with default
settings all three active declarative sources are NOT live-runnable;
specs were not weakened to obtain green.

## No bypass

See above. Settings are never rewritten automatically to pass.

## HttpFetcher remains safety enforcement owner

The hook only COMPARES declared requirements against effective
configuration. Pacing/retry/circuit-breaker/budget enforcement stays
in `HttpFetcher`; no duplicate machinery in the adapter.

## No new safety capability added in this patch

Long pauses, consecutive-error counters, per-source fetchers: all
explicitly deferred. `declarative source safely BLOCKED` is the
intended success state until those are designed.
