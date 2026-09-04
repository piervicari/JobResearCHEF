"""Failure-isolated orchestration over deduplicated Portal Registry targets."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_agent.config import ScannerSettings
from research_agent.db.migrations import create_schema
from research_agent.db.models import Portal, PortalScanAttempt, ScanRun, utc_now
from research_agent.pipeline.cache import FileResponseCache
from research_agent.pipeline.http import FetchAttempt, FetchError, HttpFetcher
from research_agent.sources.base import (
    AdapterRegistry,
    PortalScanContext,
    PortalTarget,
    RawJob,
)


@dataclass(frozen=True)
class PortalScanResult:
    target: PortalTarget
    adapter: str
    status: str
    started_at: datetime
    finished_at: datetime
    jobs: tuple[RawJob, ...]
    fetch_attempts: tuple[FetchAttempt, ...]
    retry_count: int
    final_http_status: int | None
    response_sha256: str | None
    cache_hit: bool
    complete_snapshot: bool
    warnings: tuple[str, ...] = ()
    final_url: str | None = None
    error_type: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class ScanSummary:
    scan_run_id: int
    status: str
    portal_count: int
    success_count: int
    failure_count: int
    request_count: int
    retry_count: int
    jobs_discovered: int
    portal_results: tuple[PortalScanResult, ...]


def load_portal_targets(
    engine: Engine,
    *,
    portal_ids: set[int] | None = None,
    limit: int | None = None,
    include_disabled: bool = False,
) -> list[PortalTarget]:
    """Resolve scan-eligible Portal rows to PortalTarget objects.

    `include_disabled=True` is only meaningful with an explicit `portal_ids` set.
    It allows probing a single `READY_TO_PROBE` portal whose `scan_enabled` flag
    is intentionally `False` (operational sources land in this state after the
    V25.1 sync unless an operator opts them in). The flag never modifies the
    database; the next normal scan still honours `scan_enabled`.
    """
    if include_disabled and portal_ids is None:
        raise ValueError("include_disabled requires an explicit portal_ids set")
    with Session(engine) as session:
        statement = (
            select(Portal)
            .where(Portal.active_in_registry.is_(True))
            .order_by(Portal.host, Portal.normalized_jobs_url)
        )
        if not include_disabled:
            statement = statement.where(Portal.scan_enabled.is_(True))
        if portal_ids is not None:
            statement = statement.where(Portal.id.in_(portal_ids))
        if limit is not None:
            statement = statement.limit(limit)
        portals = session.scalars(statement).all()
    return [
        PortalTarget(
            portal_id=portal.id,
            jobs_search_url=portal.jobs_search_url,
            normalized_jobs_url=portal.normalized_jobs_url,
            host=portal.host,
            ats_families=tuple(json.loads(portal.ats_families_json)),
            ats_confidences=tuple(json.loads(portal.ats_confidences_json)),
        )
        for portal in portals
    ]


async def scan_portals(
    engine: Engine,
    adapters: AdapterRegistry,
    settings: ScannerSettings,
    *,
    portal_ids: set[int] | None = None,
    limit: int | None = None,
    allow_all: bool = False,
    ignore_cooldowns: bool = False,
    include_disabled: bool = False,
    transport: httpx.AsyncBaseTransport | None = None,
    cache_directory: Path | None = None,
    run_source: str = "official_portals",
) -> ScanSummary:
    create_schema(engine)
    if include_disabled and portal_ids is None:
        raise ValueError("include_disabled requires an explicit portal_ids set")
    if include_disabled and limit is not None:
        raise ValueError("--include-disabled cannot be combined with --limit")
    if portal_ids is None and limit is None and not allow_all:
        raise ValueError(
            "Safety gate: select portal_ids or a limit; pass allow_all=True only for an "
            "explicit full-registry run"
        )
    if limit is not None and limit < 1:
        raise ValueError("limit must be at least 1")
    targets = load_portal_targets(
        engine, portal_ids=portal_ids, limit=limit, include_disabled=include_disabled
    )
    if not targets:
        raise ValueError("No active portals selected")

    with Session(engine) as session, session.begin():
        run = ScanRun(
            source=run_source,
            status="RUNNING",
            started_at=utc_now(),
            portal_count=len(targets),
            config_snapshot_json=json.dumps(
                settings.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            ),
        )
        session.add(run)
        session.flush()
        run_id = run.id

    now = utc_now()
    initially_blocked_hosts: dict[str, str] = {}
    if not ignore_cooldowns:
        with Session(engine) as session:
            cooled = session.scalars(
                select(Portal).where(Portal.cooldown_until.is_not(None))
            ).all()
        initially_blocked_hosts = {
            portal.host: portal.last_block_reason or "persisted cooldown"
            for portal in cooled
            if portal.cooldown_until is not None and _as_utc(portal.cooldown_until) > now
        }

    cache_path = cache_directory or settings.cache_directory
    fetcher = HttpFetcher(
        global_concurrency=settings.global_concurrency,
        per_domain_concurrency=settings.per_domain_concurrency,
        per_domain_min_interval_seconds=settings.per_domain_min_interval_seconds,
        request_timeout_seconds=settings.request_timeout_seconds,
        max_retries=settings.max_retries,
        backoff_base_seconds=settings.backoff_base_seconds,
        backoff_max_seconds=settings.backoff_max_seconds,
        max_retry_after_seconds=settings.max_retry_after_seconds,
        jitter_seconds=settings.jitter_seconds,
        max_response_bytes=settings.max_response_bytes,
        max_redirects=settings.max_redirects,
        max_requests_per_host_per_run=settings.max_requests_per_host_per_run,
        max_requests_per_run=settings.max_requests_per_run,
        allow_private_networks=settings.allow_private_networks,
        allow_https_to_http_redirects=settings.allow_https_to_http_redirects,
        user_agent=settings.resolved_user_agent,
        initially_blocked_hosts=initially_blocked_hosts,
        cache=FileResponseCache(cache_path),
        transport=transport,
        resolve_dns=transport is None,
    )

    async def _scan_one(target: PortalTarget) -> PortalScanResult:
        started_at = utc_now()
        adapter = adapters.select(target)
        if adapter is None:
            return PortalScanResult(
                target=target,
                adapter="none",
                status="UNSUPPORTED",
                started_at=started_at,
                finished_at=utc_now(),
                jobs=(),
                fetch_attempts=(),
                retry_count=0,
                final_http_status=None,
                response_sha256=None,
                cache_hit=False,
                complete_snapshot=False,
                warnings=(),
                error_type="UnsupportedPortal",
                error_message=f"No adapter supports ATS metadata {target.ats_families}",
            )

        # For one-shot structured catalog APIs (for example Greenhouse/Ashby),
        # receiving hundreds of records does not mean hundreds of network requests.
        # Preserve the full response while keeping the same strict request/page budget.
        record_cap = (
            settings.bulk_catalog_max_jobs_per_portal
            if getattr(adapter, "bulk_catalog", False)
            else settings.max_jobs_per_portal
        )
        context = PortalScanContext(
            fetcher=fetcher,
            max_pages_per_portal=settings.max_pages_per_portal,
            max_jobs_per_portal=record_cap,
        )
        try:
            adapter_result = await adapter.scan(target, context)
            fetch_attempts = tuple(attempt for group in context.attempt_groups for attempt in group)
            retry_count = _retry_count(context.attempt_groups)
            final_fetch = context.fetches[-1] if context.fetches else None
            return PortalScanResult(
                target=target,
                adapter=adapter.name,
                status="SUCCESS",
                started_at=started_at,
                finished_at=utc_now(),
                jobs=adapter_result.jobs,
                fetch_attempts=fetch_attempts,
                retry_count=retry_count,
                final_http_status=(final_fetch.network_status_code if final_fetch else None),
                response_sha256=(final_fetch.response_sha256 if final_fetch else None),
                cache_hit=any(fetch.from_cache for fetch in context.fetches),
                complete_snapshot=adapter_result.is_complete_snapshot,
                warnings=adapter_result.warnings,
                final_url=(final_fetch.final_url if final_fetch else None),
            )
        except Exception as exc:  # isolation boundary: one portal must never stop the run
            fetch_attempts = tuple(attempt for group in context.attempt_groups for attempt in group)
            retry_count = _retry_count(context.attempt_groups)
            if isinstance(exc, FetchError) and (
                not context.attempt_groups or context.attempt_groups[-1] != exc.attempts
            ):
                fetch_attempts += exc.attempts
                retry_count += _retry_count((exc.attempts,))
            final_status = next(
                (
                    attempt.status_code
                    for attempt in reversed(fetch_attempts)
                    if attempt.status_code is not None
                ),
                None,
            )
            return PortalScanResult(
                target=target,
                adapter=adapter.name,
                status="FAILED",
                started_at=started_at,
                finished_at=utc_now(),
                jobs=(),
                fetch_attempts=fetch_attempts,
                retry_count=retry_count,
                final_http_status=final_status,
                response_sha256=None,
                cache_hit=any(fetch.from_cache for fetch in context.fetches),
                complete_snapshot=False,
                warnings=(),
                error_type=type(exc).__name__,
                error_message=str(exc)[:2000],
            )

    async with fetcher:
        tasks = {asyncio.create_task(_scan_one(target)): target for target in targets}
        done, pending = await asyncio.wait(tasks, timeout=settings.run_timeout_seconds)
        completed = {tasks[task].portal_id: task.result() for task in done}
        timed_out_at = utc_now()
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        results = tuple(
            completed.get(target.portal_id)
            or PortalScanResult(
                target=target,
                adapter=(
                    adapter.name if (adapter := adapters.select(target)) is not None else "none"
                ),
                status="FAILED",
                started_at=timed_out_at,
                finished_at=timed_out_at,
                jobs=(),
                fetch_attempts=(),
                retry_count=0,
                final_http_status=None,
                response_sha256=None,
                cache_hit=False,
                complete_snapshot=False,
                warnings=(),
                error_type="ScanRunTimeout",
                error_message=(
                    f"Overall scan budget of {settings.run_timeout_seconds} seconds exceeded"
                ),
            )
            for target in targets
        )
    successful = [result for result in results if result.status == "SUCCESS"]
    failed = [result for result in results if result.status != "SUCCESS"]
    all_attempts = [attempt for result in results for attempt in result.fetch_attempts]
    status_counts = {group: 0 for group in (2, 3, 4, 5)}
    for attempt in all_attempts:
        if attempt.status_code is not None and attempt.status_code // 100 in status_counts:
            status_counts[attempt.status_code // 100] += 1

    block_reasons: dict[str, str] = {}
    for result in results:
        if result.final_http_status in {401, 403, 429}:
            block_reasons[result.target.host] = f"HTTP {result.final_http_status}"
        elif result.error_type in {"AccessChallengeError", "RobotsDisallowed"}:
            block_reasons[result.target.host] = result.error_type

    with Session(engine) as session, session.begin():
        run = session.get(ScanRun, run_id)
        if run is None:
            raise RuntimeError(f"Scan run {run_id} disappeared")
        for result in results:
            if result.target.portal_id is None:
                raise RuntimeError("Network scanner received a non-portal target")
            session.add(
                PortalScanAttempt(
                    scan_run_id=run_id,
                    portal_id=result.target.portal_id,
                    adapter=result.adapter,
                    status=result.status,
                    started_at=result.started_at,
                    finished_at=result.finished_at,
                    http_status=result.final_http_status,
                    retries=result.retry_count,
                    jobs_observed=len(result.jobs),
                    snapshot_complete=result.complete_snapshot,
                    response_sha256=result.response_sha256,
                    cache_hit=result.cache_hit,
                    warnings_json=json.dumps(
                        result.warnings, ensure_ascii=False, separators=(",", ":")
                    ),
                    error_type=result.error_type,
                    error_message=result.error_message,
                )
            )
            portal = session.get(Portal, result.target.portal_id)
            if portal is None:
                continue
            if result.final_http_status is not None:
                portal.last_http_status = result.final_http_status
            if result.final_url and result.final_url != result.target.jobs_search_url:
                portal.last_redirect_target = result.final_url
            if result.status == "SUCCESS":
                portal.health_state = "HEALTHY"
                portal.last_successful_scan_at = result.finished_at
                portal.consecutive_failures = 0
                if result.target.host not in block_reasons:
                    portal.cooldown_until = None
                    portal.last_block_reason = None
            elif result.status == "FAILED":
                portal.last_failure_at = result.finished_at
                portal.consecutive_failures += 1
                portal.health_state = "BROKEN" if portal.consecutive_failures >= 3 else "DEGRADED"

        if settings.host_cooldown_hours > 0:
            cooldown_until = utc_now() + timedelta(hours=settings.host_cooldown_hours)
            for host, reason in block_reasons.items():
                host_portals = session.scalars(select(Portal).where(Portal.host == host)).all()
                for portal in host_portals:
                    portal.cooldown_until = cooldown_until
                    portal.last_block_reason = reason

        run.status = "COMPLETED" if not failed else "COMPLETED_WITH_ERRORS"
        run.finished_at = utc_now()
        run.success_count = len(successful)
        run.failure_count = len(failed)
        run.request_count = len(all_attempts)
        run.retry_count = sum(result.retry_count for result in results)
        run.http_2xx_count = status_counts[2]
        run.http_3xx_count = status_counts[3]
        run.http_4xx_count = status_counts[4]
        run.http_5xx_count = status_counts[5]
        run.http_429_count = sum(attempt.status_code == 429 for attempt in all_attempts)
        run.jobs_discovered = sum(len(result.jobs) for result in successful)
        run.error_summary_json = json.dumps(
            [
                {
                    "portal_id": result.target.portal_id,
                    "status": result.status,
                    "error_type": result.error_type,
                    "error_message": result.error_message,
                }
                for result in failed
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        status = run.status

    return ScanSummary(
        scan_run_id=run_id,
        status=status,
        portal_count=len(results),
        success_count=len(successful),
        failure_count=len(failed),
        request_count=len(all_attempts),
        retry_count=sum(result.retry_count for result in results),
        jobs_discovered=sum(len(result.jobs) for result in successful),
        portal_results=results,
    )


def _retry_count(
    groups: tuple[tuple[FetchAttempt, ...], ...] | list[tuple[FetchAttempt, ...]],
) -> int:
    return sum(max((attempt.retry_index for attempt in group), default=0) for group in groups)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
