"""Fail-closed safety preflight for declarative scans (Phase 2 hardening).

CURRENT STATE (documented, not hidden): ``DeclarativeSourceAdapter.scan()``
does not read ``spec["safety"]``. Network safety stays solely owned by
``HttpFetcher``/``Scanner``. This module is the bridge between the two:
a pure, source-agnostic comparison of what a spec REQUIRES versus what
the effective scanner configuration PROVIDES. No networking, no retry,
no pacing here — just a verdict before any live run.

Verdicts:

- ``SAFE_TO_RUN`` — every active spec requirement is covered.
- ``UNSUPPORTED_SAFETY_REQUIREMENT`` — the spec demands something no
  existing fetcher/scanner mechanism provides (fail closed).
- ``SCANNER_SETTINGS_TOO_PERMISSIVE`` — the mechanism exists but the
  configured values are weaker than the spec demands (fail closed).

There is deliberately no bypass flag. A declarative source whose
preflight is not SAFE_TO_RUN must not be scanned live.

Requirement mapping (spec field -> class):

- ``sequential_only`` ............ CAN_VALIDATE_AGAINST_GLOBAL_SETTINGS
  (requires effective per_domain_concurrency == 1)
- ``min_seconds_between_requests`` CAN_VALIDATE_AGAINST_GLOBAL_SETTINGS
  (requires effective per_domain_min_interval_seconds >= value)
- ``max_requests_per_run`` ........ CAN_VALIDATE_AGAINST_GLOBAL_SETTINGS
  (requires effective max_requests_per_run <= value; the spec states
  the source's per-run tolerance, the scanner must stay within it)
- ``abort_on_http_403`` .......... ENFORCED_BY_EXISTING_FETCHER
  (fetcher circuit-breaker statuses always include 401/403/429)
- ``abort_on_http_429`` .......... ENFORCED_BY_EXISTING_FETCHER
  (429 raises HostCircuitOpenError immediately, never retried)
- ``max_retries_on_5xx`` ......... CAN_VALIDATE_AGAINST_GLOBAL_SETTINGS
  (requires effective max_retries <= value; note the fetcher retry set
  is {500,502,503,504} plus transport errors — 429 excluded)
- ``long_pause_every_n_requests`` / ``long_pause_seconds``
  ............................... NOT_CURRENTLY_SUPPORTED
  (no fetcher/scanner mechanism for periodic long pauses)
- ``max_consecutive_errors`` ..... NOT_CURRENTLY_SUPPORTED
  (no consecutive-error counter; the fetcher blocks hosts permanently
  on 401/403/429 instead, which is a different philosophy)

A NOT_CURRENTLY_SUPPORTED requirement with an active (non-zero/true)
value fails the preflight. This is intentional: it honestly reveals
that, today, no declarative source with such a requirement is
live-runnable — implementing the missing harness capability is future
work, explicitly NOT an adapter-side second engine and NOT a reason to
loosen the spec silently.
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

    min_interval = active("min_seconds_between_requests") or 0
    if min_interval and effective.per_domain_min_interval_seconds < min_interval:
        permissive.append(
            f"min_seconds_between_requests={min_interval} requires "
            "per_domain_min_interval_seconds>=that, scanner has "
            f"{effective.per_domain_min_interval_seconds}"
        )

    spec_run_budget = active("max_requests_per_run")
    if spec_run_budget and effective.max_requests_per_run > spec_run_budget:
        permissive.append(
            f"max_requests_per_run={spec_run_budget} exceeded by scanner "
            f"max_requests_per_run={effective.max_requests_per_run}"
        )

    if active("abort_on_http_403") and 403 not in effective.circuit_breaker_statuses:
        unsupported.append("abort_on_http_403=true but 403 is not a circuit-breaker status")
    if active("abort_on_http_429") and 429 not in effective.circuit_breaker_statuses:
        unsupported.append("abort_on_http_429=true but 429 is not a circuit-breaker status")

    max_retries = active("max_retries_on_5xx")
    if max_retries is not None and effective.max_retries > max_retries:
        permissive.append(
            f"max_retries_on_5xx={max_retries} exceeded by scanner "
            f"max_retries={effective.max_retries}"
        )

    if active("long_pause_every_n_requests") or active("long_pause_seconds"):
        unsupported.append(
            "long_pause_every_n_requests/long_pause_seconds is active but "
            "NOT_CURRENTLY_SUPPORTED by any fetcher/scanner mechanism"
        )

    if active("max_consecutive_errors"):
        unsupported.append(
            "max_consecutive_errors is active but NOT_CURRENTLY_SUPPORTED "
            "(no consecutive-error counter in fetcher/scanner)"
        )

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
