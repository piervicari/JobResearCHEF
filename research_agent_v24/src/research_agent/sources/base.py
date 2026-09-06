"""Contracts shared by all vacancy source adapters."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Protocol

from research_agent.pipeline.http import (
    AccessChallengeError,
    FetchAttempt,
    FetchError,
    FetchRequest,
    FetchResponse,
    HostCircuitOpenError,
    HttpFetcher,
    ScanWirePolicy,
)


@dataclass(frozen=True)
class PortalTarget:
    portal_id: int | None
    jobs_search_url: str
    normalized_jobs_url: str
    host: str
    ats_families: tuple[str, ...]
    ats_confidences: tuple[str, ...]


@dataclass(frozen=True)
class RawJob:
    source: str
    source_job_id: str
    source_url: str
    apply_url: str
    title: str
    company: str = ""
    location: str = ""
    country: str | None = None
    city: str | None = None
    description: str = ""
    posted_at: datetime | None = None
    employment_type: str | None = None
    workplace_type: str | None = None
    ats_job_id: str | None = None
    requisition_id: str | None = None
    raw_payload: dict[str, object] | None = None


@dataclass(frozen=True)
class AdapterScanResult:
    jobs: tuple[RawJob, ...] = ()
    warnings: tuple[str, ...] = ()
    is_complete_snapshot: bool = False


class ScanRequestBudgetExceeded(RuntimeError):
    """A per-scan wire-attempt budget was exhausted before the next fetch.

    Raised by ``PortalScanContext.fetch`` instead of performing another
    request. Not a ``FetchError``: no wire attempt was made. Adapters catch
    it, keep partial results, and finish with ``is_complete_snapshot=False``.
    """


class MaxConsecutiveErrorsExceeded(RuntimeError):
    """A per-scan consecutive-failure budget was exhausted.

    Raised instead of the last fetch error once ``max_consecutive_errors``
    logical fetches in a row have failed. Success resets the counter.
    Immediate-abort signals (403/429/challenge) never pass through here:
    they propagate unchanged with zero further requests.
    """


@dataclass
class PortalScanContext:
    fetcher: HttpFetcher
    max_pages_per_portal: int = 30
    max_jobs_per_portal: int = 500
    fetches: list[FetchResponse] = field(default_factory=list)
    attempt_groups: list[tuple[FetchAttempt, ...]] = field(default_factory=list)
    # Optional generic per-scan safety policies. All default to "legacy
    # behavior" (no cap, no consecutive budget, first error propagates) so
    # adapters that never configure them scan exactly as before. A context
    # instance lives for exactly one portal scan, so every counter below is
    # per-scan by construction. Units:
    # - max_requests is a HARD cap on WIRE attempts (retries/redirects
    #   included), enforced by HttpFetcher at the real outbound attempt
    #   point via the per-scan ScanWirePolicy — overshoot is impossible;
    # - long pauses are WIRE-based (see ScanWirePolicy), not logical-fetch
    #   based;
    # - consecutive errors count failed LOGICAL fetches after the fetcher's
    #   normal retry handling.
    max_requests: int | None = None
    max_consecutive_errors: int | None = None

    def __post_init__(self) -> None:
        if self.max_requests is not None and self.max_requests < 1:
            raise ValueError("max_requests must be at least 1")
        if self.max_consecutive_errors is not None and self.max_consecutive_errors < 1:
            raise ValueError("max_consecutive_errors must be at least 1")
        self._wire_attempts = 0
        self._consecutive_errors = 0
        self._wire_policy: ScanWirePolicy | None = None

    @property
    def wire_attempts(self) -> int:
        """Post-hoc observation of wire attempts so far (always <= cap).

        Enforcement source of truth is the ScanWirePolicy mutated by the
        fetcher; this counter reconciles it from recorded attempts.
        """
        return self._wire_attempts

    @property
    def consecutive_errors(self) -> int:
        return self._consecutive_errors

    @property
    def wire_policy(self) -> ScanWirePolicy | None:
        return self._wire_policy

    def configure_scan_limits(
        self,
        *,
        max_requests: int | None = None,
        long_pause_every_n_requests: int = 0,
        long_pause_seconds: float = 0.0,
        max_consecutive_errors: int | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        """Wire source-declared per-scan policy into this scan's funnel.

        Generic orchestration hook: any adapter may call it once before its
        fetch loop with values from its own source contract. Builds the
        per-scan ScanWirePolicy that HttpFetcher enforces (hard wire cap +
        wire-based pauses). Values only restrict (caps/pauses/budgets); they
        cannot loosen the shared fetcher configuration. Must be called
        before the first fetch.
        """
        if self._wire_attempts or self._consecutive_errors or self._wire_policy is not None:
            raise ValueError("scan limits must be configured before the first fetch")
        self.max_requests = max_requests
        self.max_consecutive_errors = max_consecutive_errors
        self.__post_init__()
        if (
            max_requests is not None
            or long_pause_every_n_requests
            or long_pause_seconds
        ):
            self._wire_policy = ScanWirePolicy(
                max_wire_attempts=max_requests,
                pause_every_n_attempts=long_pause_every_n_requests,
                pause_seconds=long_pause_seconds,
                sleep=sleep,
            )

    async def fetch(self, request: FetchRequest) -> FetchResponse:
        if (
            self.max_consecutive_errors is not None
            and self._consecutive_errors >= self.max_consecutive_errors
        ):
            # Budget already exhausted by earlier failures: raise without
            # touching the transport — zero requests after stop.
            raise MaxConsecutiveErrorsExceeded(
                f"{self._consecutive_errors} consecutive fetch failures "
                f"(budget {self.max_consecutive_errors}); stopping conservatively"
            )
        if self._wire_policy is not None and self._wire_policy.exhausted():
            raise ScanRequestBudgetExceeded(
                f"per-scan wire budget of {self._wire_policy.max_wire_attempts} "
                f"exhausted after {self._wire_policy.used_wire_attempts} wire attempts"
            )
        if self._wire_policy is not None and request.wire_policy is None:
            request = replace(request, wire_policy=self._wire_policy)
        try:
            response = await self.fetcher.fetch(request)
        except (HostCircuitOpenError, AccessChallengeError) as exc:
            # Immediate-abort signals: propagate unchanged, no consecutive
            # counting, zero further requests by the caller.
            self.attempt_groups.append(exc.attempts)
            raise
        except FetchError as exc:
            self._wire_attempts += len(exc.attempts)
            self._consecutive_errors += 1
            self.attempt_groups.append(exc.attempts)
            if (
                self.max_consecutive_errors is not None
                and self._consecutive_errors >= self.max_consecutive_errors
            ):
                raise MaxConsecutiveErrorsExceeded(
                    f"{self._consecutive_errors} consecutive fetch failures "
                    f"(budget {self.max_consecutive_errors}); stopping conservatively"
                ) from exc
            raise
        self._wire_attempts += len(response.attempts)
        self._consecutive_errors = 0
        self.fetches.append(response)
        self.attempt_groups.append(response.attempts)
        return response

    def page_limit(self, adapter_limit: int) -> int:
        return min(adapter_limit, self.max_pages_per_portal)


class SourceAdapter(Protocol):
    name: str

    def supports(self, target: PortalTarget) -> bool: ...

    async def scan(
        self, target: PortalTarget, context: PortalScanContext
    ) -> AdapterScanResult: ...


# Optional generic preflight hook (NOT part of the Protocol on purpose:
# legacy adapters must not be forced to implement it). An adapter MAY
# define `preflight(target, settings) -> None`, which the normal Scanner
# path invokes after select() and before anything that could touch the
# network. Contract: return None when safe, raise when unsafe (fail
# closed); any non-None return is itself treated as a contract
# violation. Adapters without the hook scan exactly as before.


class AdapterRegistry:
    def __init__(self, adapters: list[SourceAdapter]) -> None:
        self._adapters = tuple(adapters)

    def select(self, target: PortalTarget) -> SourceAdapter | None:
        return next((adapter for adapter in self._adapters if adapter.supports(target)), None)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(adapter.name for adapter in self._adapters)
