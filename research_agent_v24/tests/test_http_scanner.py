import asyncio
import json
import time
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_agent.config import ScannerSettings
from research_agent.db.migrations import create_schema
from research_agent.db.models import ImportBatch, Portal, PortalScanAttempt, ScanRun
from research_agent.pipeline.cache import FileResponseCache
from research_agent.pipeline.http import FetchRequest, HostCircuitOpenError, HttpFetcher
from research_agent.pipeline.scanner import scan_portals
from research_agent.sources.base import (
    AdapterRegistry,
    AdapterScanResult,
    PortalScanContext,
    PortalTarget,
    RawJob,
)


def test_http_fetcher_opens_circuit_on_first_429() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, headers={"Retry-After": "0"}, request=request)

    async def run() -> None:
        fetcher = HttpFetcher(
            max_retries=2,
            per_domain_min_interval_seconds=0,
            jitter_seconds=0,
            resolve_dns=False,
            transport=httpx.MockTransport(handler),
        )
        async with fetcher:
            with pytest.raises(HostCircuitOpenError) as raised:
                await fetcher.fetch(FetchRequest("https://jobs.example.test/openings"))
            assert [attempt.status_code for attempt in raised.value.attempts] == [429]

    asyncio.run(run())
    assert calls == 1


def test_http_fetcher_uses_conditional_cache(tmp_path: Path) -> None:
    seen_if_none_match: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        validator = request.headers.get("If-None-Match")
        seen_if_none_match.append(validator)
        if validator == '"v1"':
            return httpx.Response(304, request=request)
        return httpx.Response(
            200,
            content=b'{"jobs":[{"id":"1"}]}',
            headers={"ETag": '"v1"', "Content-Type": "application/json; charset=utf-8"},
            request=request,
        )

    async def run() -> None:
        fetcher = HttpFetcher(
            max_retries=0,
            per_domain_min_interval_seconds=0,
            jitter_seconds=0,
            cache=FileResponseCache(tmp_path / "cache"),
            resolve_dns=False,
            transport=httpx.MockTransport(handler),
        )
        async with fetcher:
            first = await fetcher.fetch(FetchRequest("https://jobs.example.test/openings"))
            second = await fetcher.fetch(FetchRequest("https://jobs.example.test/openings"))
            assert first.from_cache is False
            assert second.from_cache is True
            assert second.not_modified is True
            assert second.network_status_code == 304
            assert second.status_code == 200
            assert second.content == first.content

    asyncio.run(run())
    assert seen_if_none_match == [None, '"v1"']


def test_domain_rate_limiter_spaces_concurrent_requests() -> None:
    started: list[float] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        started.append(time.monotonic())
        return httpx.Response(200, text="ok", request=request)

    async def run() -> None:
        fetcher = HttpFetcher(
            global_concurrency=3,
            per_domain_concurrency=3,
            per_domain_min_interval_seconds=0.02,
            max_retries=0,
            jitter_seconds=0,
            resolve_dns=False,
            transport=httpx.MockTransport(handler),
        )
        async with fetcher:
            await asyncio.gather(
                *(
                    fetcher.fetch(FetchRequest(f"https://same.example.test/{index}"))
                    for index in range(3)
                )
            )

    asyncio.run(run())
    assert len(started) == 3
    assert all(
        later - earlier >= 0.015 for earlier, later in zip(started, started[1:], strict=False)
    )


class _IsolationAdapter:
    name = "isolation-fixture"

    def supports(self, target: PortalTarget) -> bool:
        return True

    async def scan(self, target: PortalTarget, context: PortalScanContext) -> AdapterScanResult:
        if target.host.startswith("bad"):
            raise ValueError("fixture parser failure")
        return AdapterScanResult(
            jobs=(
                RawJob(
                    source=self.name,
                    source_job_id="job-1",
                    source_url=target.jobs_search_url,
                    apply_url=target.jobs_search_url + "/1",
                    title="Junior Security Analyst",
                ),
            ),
            warnings=("fixture warning",),
        )


class _SlowAdapter:
    name = "slow-fixture"

    def supports(self, target: PortalTarget) -> bool:
        return True

    async def scan(self, target: PortalTarget, context: PortalScanContext) -> AdapterScanResult:
        await asyncio.sleep(0.1)
        return AdapterScanResult()


class _FetchingAdapter:
    name = "fetching-fixture"

    def supports(self, target: PortalTarget) -> bool:
        return True

    async def scan(self, target: PortalTarget, context: PortalScanContext) -> AdapterScanResult:
        response = await context.fetch(FetchRequest(target.jobs_search_url))
        if response.status_code != 200:
            raise ValueError(f"HTTP {response.status_code}")
        return AdapterScanResult()


def _seed_two_portals(engine: Engine) -> None:
    create_schema(engine)
    with Session(engine) as session, session.begin():
        batch = ImportBatch(
            source_kind="test",
            source_filename="fixture.csv",
            source_path="fixture.csv",
            source_sha256="f" * 64,
            source_version="test",
            status="COMPLETED",
        )
        session.add(batch)
        session.flush()
        for host in ("good.example.test", "bad.example.test"):
            session.add(
                Portal(
                    normalized_jobs_url=f"https://{host}/jobs",
                    jobs_search_url=f"https://{host}/jobs",
                    scheme="https",
                    host=host,
                    ats_families_json=json.dumps(["fixture"]),
                    ats_confidences_json=json.dumps(["Verified"]),
                    metadata_conflict=False,
                    cluster_count=1,
                    active_in_registry=True,
                    health_state="UNKNOWN",
                    consecutive_failures=0,
                    import_batch_id=batch.id,
                )
            )


def test_scanner_isolates_portal_failures_and_persists_metrics(
    sqlite_engine: Engine, tmp_path: Path
) -> None:
    _seed_two_portals(sqlite_engine)
    settings = ScannerSettings(
        per_domain_min_interval_seconds=0,
        jitter_seconds=0,
        cache_directory=tmp_path / "cache",
    )
    summary = asyncio.run(
        scan_portals(
            sqlite_engine,
            AdapterRegistry([_IsolationAdapter()]),
            settings,
            limit=2,
            cache_directory=tmp_path / "cache",
        )
    )

    assert summary.status == "COMPLETED_WITH_ERRORS"
    assert summary.portal_count == 2
    assert summary.success_count == 1
    assert summary.failure_count == 1
    assert summary.jobs_discovered == 1

    with Session(sqlite_engine) as session:
        run = session.get(ScanRun, summary.scan_run_id)
        assert run is not None
        assert run.success_count == 1
        assert run.failure_count == 1
        attempts = session.scalars(select(PortalScanAttempt)).all()
        assert {attempt.status for attempt in attempts} == {"SUCCESS", "FAILED"}
        success = next(attempt for attempt in attempts if attempt.status == "SUCCESS")
        assert json.loads(success.warnings_json) == ["fixture warning"]
        portals = session.scalars(select(Portal)).all()
        health = {portal.host: portal.health_state for portal in portals}
        assert health["good.example.test"] == "HEALTHY"
        assert health["bad.example.test"] == "DEGRADED"


def test_scanner_marks_unfinished_portals_failed_at_overall_timeout(
    sqlite_engine: Engine, tmp_path: Path
) -> None:
    _seed_two_portals(sqlite_engine)
    settings = ScannerSettings(
        run_timeout_seconds=0.01,
        per_domain_min_interval_seconds=0,
        jitter_seconds=0,
        cache_directory=tmp_path / "cache",
    )

    summary = asyncio.run(
        scan_portals(
            sqlite_engine,
            AdapterRegistry([_SlowAdapter()]),
            settings,
            limit=2,
            cache_directory=tmp_path / "cache",
        )
    )

    assert summary.status == "COMPLETED_WITH_ERRORS"
    assert summary.failure_count == 2
    assert {result.error_type for result in summary.portal_results} == {"ScanRunTimeout"}


def test_scanner_persists_and_honors_host_cooldown(
    sqlite_engine: Engine, tmp_path: Path
) -> None:
    _seed_two_portals(sqlite_engine)
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host or "")
        status = 403 if request.url.host == "bad.example.test" else 200
        return httpx.Response(status, text="denied" if status == 403 else "ok", request=request)

    settings = ScannerSettings(
        host_cooldown_hours=24,
        per_domain_min_interval_seconds=0,
        jitter_seconds=0,
        cache_directory=tmp_path / "cache",
    )
    first = asyncio.run(
        scan_portals(
            sqlite_engine,
            AdapterRegistry([_FetchingAdapter()]),
            settings,
            limit=2,
            transport=httpx.MockTransport(handler),
            cache_directory=tmp_path / "cache",
        )
    )
    assert first.failure_count == 1

    with Session(sqlite_engine) as session:
        bad = session.scalar(select(Portal).where(Portal.host == "bad.example.test"))
        assert bad is not None
        assert bad.cooldown_until is not None
        assert bad.last_block_reason == "HTTP 403"
        bad_id = bad.id

    calls_before = len(calls)
    second = asyncio.run(
        scan_portals(
            sqlite_engine,
            AdapterRegistry([_FetchingAdapter()]),
            settings,
            portal_ids={bad_id},
            transport=httpx.MockTransport(handler),
            cache_directory=tmp_path / "cache",
        )
    )
    assert second.failure_count == 1
    assert second.portal_results[0].error_type == "HostCircuitOpenError"
    assert len(calls) == calls_before


def test_embedded_turnstile_widget_is_not_treated_as_access_challenge() -> None:
    html = b'''<html><head><title>Threat Intelligence analyst</title></head>
    <body><main><h1>Threat Intelligence analyst</h1><p>Full job content.</p></main>
    <form><div class="cf-turnstile" data-sitekey="example"></div></form></body></html>'''
    assert HttpFetcher._contains_challenge(html) is False


def test_cloudflare_interstitial_still_counts_as_access_challenge() -> None:
    html = b'''<html><head><title>Just a moment...</title></head>
    <body><div id="cf-chl-widget">Verify you are human</div></body></html>'''
    assert HttpFetcher._contains_challenge(html) is True


def test_scan_portals_include_disabled_requires_explicit_portal_ids(
    sqlite_engine: Engine, tmp_path: Path
) -> None:
    """scan_portals(include_disabled=True) is only valid with an explicit
    portal_ids set and cannot be combined with limit."""
    settings = ScannerSettings()
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jobs": []})
    # 1) No portal_ids → ValueError.
    with pytest.raises(ValueError, match="include_disabled requires an explicit portal_ids set"):
        asyncio.run(
            scan_portals(
                sqlite_engine,
                AdapterRegistry([_FetchingAdapter()]),
                settings,
                include_disabled=True,
                transport=httpx.MockTransport(handler),
                cache_directory=tmp_path / "cache",
            )
        )
    # 2) limit + include_disabled → ValueError.
    with pytest.raises(ValueError, match="--include-disabled cannot be combined with --limit"):
        asyncio.run(
            scan_portals(
                sqlite_engine,
                AdapterRegistry([_FetchingAdapter()]),
                settings,
                portal_ids={1},
                limit=1,
                include_disabled=True,
                transport=httpx.MockTransport(handler),
                cache_directory=tmp_path / "cache",
            )
        )


def test_http_fetcher_supports_form_encoded_post_without_json_body() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["content_type"] = request.headers.get("Content-Type", "")
        seen["body"] = request.content.decode()
        return httpx.Response(200, text="ok", request=request)

    async def run() -> None:
        fetcher = HttpFetcher(
            max_retries=0,
            per_domain_min_interval_seconds=0,
            jitter_seconds=0,
            resolve_dns=False,
            transport=httpx.MockTransport(handler),
        )
        async with fetcher:
            await fetcher.fetch(
                FetchRequest(
                    "https://jobs.example.test/rpc",
                    method="POST",
                    form_body={"f.req": "payload"},
                )
            )

    asyncio.run(run())
    assert seen["method"] == "POST"
    assert seen["content_type"].startswith("application/x-www-form-urlencoded")
    assert seen["body"] == "f.req=payload"
