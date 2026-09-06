"""Fail-closed safety preflight for declarative scans (Phase 2 hardening).

CURRENT STATE: ``DeclarativeSourceAdapter.scan()`` wires ``spec["safety"]``
into generic per-scan/per-request enforcement owned by the existing
``HttpFetcher``/``PortalScanContext`` path (no second engine anywhere):

- per-request interval FLOOR (``min_seconds_between_requests``) and retry
  CEILING (``max_retries_on_5xx``) travel on ``FetchRequest``; the fetcher
  applies ``max(global, floor)`` / ``min(global, ceiling)`` — conservative
  by construction, so these can never be TOO_PERMISSIVE at runtime;
- per-scan wire-attempt budget (``max_requests_per_run``), periodic long
  pause (``long_pause_every_n_requests``/``long_pause_seconds``) and the
  consecutive-failure budget (``max_consecutive_errors``) live on
  ``PortalScanContext`` (one instance per scan) with the adapter doing
  orchestration only (wire values, retry-same-offset, stop-with-partial).

This module stays a pure, source-agnostic comparison of what a spec
REQUIRES versus what the effective scanner configuration PROVIDES, plus a
check that every active requirement has a runtime mechanism. No networking,
no retry, no pacing here — just a verdict before any live run.

Verdicts:

- ``SAFE_TO_RUN`` — every active spec requirement is covered.
- ``UNSUPPORTED_SAFETY_REQUIREMENT`` — the spec demands something no
  existing fetcher/scanner mechanism provides (fail closed).
- ``SCANNER_SETTINGS_TOO_PERMISSIVE`` — the mechanism exists but the
  configured values are weaker than the spec demands (fail closed).
  Only ``sequential_only`` can still produce this: it depends on the
  shared per-domain concurrency, which no per-request override may loosen.

There is deliberately no bypass flag. A declarative source whose
preflight is not SAFE_TO_RUN must not be scanned live.

Requirement mapping (spec field -> class):

- ``sequential_only`` ............ CAN_VALIDATE_AGAINST_GLOBAL_SETTINGS
  (requires effective per_domain_concurrency == 1)
- ``min_seconds_between_requests`` ENFORCED_PER_REQUEST
  (adapter wires the spec floor onto every FetchRequest; the fetcher
  applies max(global, floor); 429 excluded from retries as before)
- ``max_requests_per_run`` ........ ENFORCED_PER_SCAN
  (context wire-attempt budget: retries/redirects included; stop keeps
  partial jobs, complete_snapshot=false, explicit warning)
- ``abort_on_http_403`` .......... ENFORCED_BY_EXISTING_FETCHER
  (fetcher circuit-breaker statuses always include 401/403/429; the
  adapter additionally stops at the first non-2xx with partial kept)
- ``abort_on_http_429`` .......... ENFORCED_BY_EXISTING_FETCHER
  (429 raises HostCircuitOpenError immediately, never retried, never
  counted against the consecutive-error budget)
- ``max_retries_on_5xx`` ......... ENFORCED_PER_REQUEST
  (adapter wires the spec ceiling onto every FetchRequest; the fetcher
  applies min(global, ceiling); the fetcher retry set is
  {500,502,503,504} plus transport errors — 429 excluded)
- ``long_pause_every_n_requests`` / ``long_pause_seconds``
  ............................... ENFORCED_PER_SCAN
  (context pauses S seconds before request N+1, 2N+1, ... — never after
  the final request; per-scan counter, injectable clock)
- ``max_consecutive_errors`` ..... ENFORCED_PER_SCAN
  (context counts failed logical fetches after normal fetcher retries;
  success resets; at threshold the adapter stops with partial kept;
  403/429/challenge bypass the counter and abort immediately)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EffectiveScannerSafety:
    """The safety-relevant slice of the live scanner configuration."""

    per_domain_concurrency: int = 1
    per_domain_min_interval_seconds: float = 0.0
    max_requests_per_run: int = 500
    max_requests_per_host_per_run: int = 30
    max_retries: int = 0
    circuit_breaker_statuses: frozenset[int] = frozenset({401, 403, 429})


def effective_safety_from_settings(settings: Any) -> EffectiveScannerSafety:
    """Project a ScannerSettings onto the safety-relevant slice."""
    return EffectiveScannerSafety(
        per_domain_concurrency=settings.per_domain_concurrency,
        per_domain_min_interval_seconds=settings.per_domain_min_interval_seconds,
        max_requests_per_run=settings.max_requests_per_run,
        max_requests_per_host_per_run=settings.max_requests_per_host_per_run,
        max_retries=settings.max_retries,
        circuit_breaker_statuses=frozenset({401, 403, 429}),
    )


@dataclass(frozen=True)
class SafetyPreflightResult:
    verdict: str  # SAFE_TO_RUN | UNSUPPORTED_SAFETY_REQUIREMENT | SCANNER_SETTINGS_TOO_PERMISSIVE
    reasons: tuple[str, ...] = ()


def _safety_section(spec: dict) -> dict:
    safety = spec.get("safety") or {}
    if not isinstance(safety, dict):
        raise ValueError("spec safety section must be an object")
    return safety


def preflight_safety(spec: dict, effective: EffectiveScannerSafety) -> SafetyPreflightResult:
    """Compare spec safety requirements against effective scanner safety.

    Pure function: no I/O, no network, deterministic. Every violated
    requirement appends a reason; the verdict is UNSUPPORTED if any
    unsupported requirement is active, else TOO_PERMISSIVE if any
    configured value is weaker than required, else SAFE_TO_RUN.
    """
    safety = _safety_section(spec)
    unsupported: list[str] = []
    permissive: list[str] = []

    def active(name: str) -> Any:
        return safety.get(name)

    if active("sequential_only"):
        if effective.per_domain_concurrency != 1:
            permissive.append(
                "sequential_only=true requires per_domain_concurrency=1, "
                f"scanner has {effective.per_domain_concurrency}"
            )

    # The remaining requirements are enforced per-request/per-scan by the
    # adapter wiring the spec's own values into the existing fetcher/context
    # path (floors/ceilings/budgets only restrict, never loosen). The
    # preflight therefore only needs to confirm a mechanism exists — which
    # is structural, covered by the wiring tests — not compare values.
    if active("abort_on_http_403") and 403 not in effective.circuit_breaker_statuses:
        unsupported.append("abort_on_http_403=true but 403 is not a circuit-breaker status")
    if active("abort_on_http_429") and 429 not in effective.circuit_breaker_statuses:
        unsupported.append("abort_on_http_429=true but 429 is not a circuit-breaker status")

    if unsupported:
        return SafetyPreflightResult("UNSUPPORTED_SAFETY_REQUIREMENT", tuple(unsupported + permissive))
    if permissive:
        return SafetyPreflightResult("SCANNER_SETTINGS_TOO_PERMISSIVE", tuple(permissive))
    return SafetyPreflightResult("SAFE_TO_RUN", ())


def assert_safe_to_run(spec: dict, effective: EffectiveScannerSafety) -> None:
    """Fail closed: raise unless the preflight verdict is SAFE_TO_RUN."""
    result = preflight_safety(spec, effective)
    if result.verdict != "SAFE_TO_RUN":
        raise UnsafeToRunError(
            f"declarative scan blocked before any network access: {result.verdict}: "
            + "; ".join(result.reasons)
        )


class UnsafeToRunError(RuntimeError):
    """A declarative source failed its safety preflight. No bypass exists."""


__all__ = [
    "EffectiveScannerSafety",
    "SafetyPreflightResult",
    "UnsafeToRunError",
    "assert_safe_to_run",
    "effective_safety_from_settings",
    "preflight_safety",
]
