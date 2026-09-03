"""Contracts shared by all vacancy source adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from research_agent.pipeline.http import (
    FetchAttempt,
    FetchError,
    FetchRequest,
    FetchResponse,
    HttpFetcher,
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


@dataclass
class PortalScanContext:
    fetcher: HttpFetcher
    max_pages_per_portal: int = 30
    max_jobs_per_portal: int = 500
    fetches: list[FetchResponse] = field(default_factory=list)
    attempt_groups: list[tuple[FetchAttempt, ...]] = field(default_factory=list)

    async def fetch(self, request: FetchRequest) -> FetchResponse:
        try:
            response = await self.fetcher.fetch(request)
        except FetchError as exc:
            self.attempt_groups.append(exc.attempts)
            raise
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


class AdapterRegistry:
    def __init__(self, adapters: list[SourceAdapter]) -> None:
        self._adapters = tuple(adapters)

    def select(self, target: PortalTarget) -> SourceAdapter | None:
        return next((adapter for adapter in self._adapters if adapter.supports(target)), None)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(adapter.name for adapter in self._adapters)
