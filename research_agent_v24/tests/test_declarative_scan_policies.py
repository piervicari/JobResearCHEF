"""Per-scan/per-request safety policy tests (offline, deterministic).

Covers the generic PortalScanContext policies (request budget, periodic
long pause, consecutive-error budget), the HttpFetcher per-request
ceilings, and their declarative-adapter wiring. Clocks/sleeps are fake;
transports are httpx.MockTransport or in-memory stubs. Zero network.
"""
from __future__ import annotations

import asyncio
import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from research_agent.pipeline.http import (
    FetchAttempt,
    FetchError,
    FetchRequest,
    FetchResponse,
    HostCircuitOpenError,
    HttpFetcher,
)
from research_agent.sources.base import (
    MaxConsecutiveErrorsExceeded,
    PortalScanContext,
    ScanRequestBudgetExceeded,
)

DECL_DIR = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "research_agent"
    / "sources"
    / "declarative"
)


def _attempt(status: int | None = 200) -> FetchAttempt:
    return FetchAttempt(status_code=status, error_type=None, elapsed_seconds=0.0)


def _ok_response(url: str, attempts: int = 1) -> FetchResponse:
    return FetchResponse(
        requested_url=url,
        final_url=url,
        status_code=200,
        network_status_code=200,
        headers={},
        content=b"{}",
        fetched_at=datetime.now(UTC),
        attempts=tuple(_attempt() for _ in range(attempts)),
        from_cache=False,
        not_modified=False,
        response_sha256="0" * 64,
    )


class _StubFetcher:
    """In-memory fetcher: scripted responses/errors, explodes when exhausted."""

    def __init__(self, script: list) -> None:
        self._script = list(script)
        self.calls = 0

    async def fetch(self, request: FetchRequest):
        self.calls += 1
        if not self._script:
            raise AssertionError("fetcher called after script exhausted (no requests after stop)")
        outcome = self._script.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class _Recorder:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def sleep(self, seconds: float) -> None:
        self.events.append(f"pause:{seconds:g}")


def _context(stub, recorder, **policy) -> PortalScanContext:
    return PortalScanContext(
        fetcher=stub,  # type: ignore[arg-type]
        max_pages_per_portal=30,
        max_jobs_per_portal=500,
        sleep=recorder.sleep,
        **policy,
    )


def _req() -> FetchRequest:
    return FetchRequest("https://unit.example.test/jobs")


# ---------- §15 periodic pause ----------

def test_periodic_pause_four_requests() -> None:
    rec = _Recorder()
    stub = _StubFetcher([_ok_response("u") for _ in range(4)])
    ctx = _context(stub, rec, long_pause_every_n_requests=3, long_pause_seconds=5.0)

    async def run():
        for _ in range(4):
            await ctx.fetch(_req())
            rec.events.append("request")

    asyncio.run(run())
    assert rec.events == ["request"] * 3 + ["pause:5", "request"]


def test_periodic_pause_exactly_three_requests_has_no_trailing_pause() -> None:
    rec = _Recorder()
    stub = _StubFetcher([_ok_response("u") for _ in range(3)])
    ctx = _context(stub, rec, long_pause_every_n_requests=3, long_pause_seconds=5.0)

    async def run():
        for _ in range(3):
            await ctx.fetch(_req())
            rec.events.append("request")

    asyncio.run(run())
    assert rec.events == ["request"] * 3


def test_periodic_pause_seven_requests() -> None:
    rec = _Recorder()
    stub = _StubFetcher([_ok_response("u") for _ in range(7)])
    ctx = _context(stub, rec, long_pause_every_n_requests=3, long_pause_seconds=5.0)

    async def run():
        for _ in range(7):
            await ctx.fetch(_req())
            rec.events.append("request")

    asyncio.run(run())
    assert rec.events == ["request"] * 3 + ["pause:5"] + ["request"] * 3 + ["pause:5", "request"]


# ---------- §16 consecutive errors ----------

def _fetch_error() -> FetchError:
    return FetchError("boom", attempts=(_attempt(None),))


def test_consecutive_errors_reset_on_success() -> None:
    rec = _Recorder()
    stub = _StubFetcher(
        [_fetch_error(), _fetch_error(), _ok_response("u"), _fetch_error(), _fetch_error()]
    )
    ctx = _context(stub, rec, max_consecutive_errors=3)

    async def run():
        for _ in range(2):
            with pytest.raises(FetchError):
                await ctx.fetch(_req())
        await ctx.fetch(_req())
        for _ in range(2):
            with pytest.raises(FetchError):
                await ctx.fetch(_req())

    asyncio.run(run())  # no stop: threshold 3 never reached consecutively
    assert stub.calls == 5


def test_consecutive_errors_stop_at_threshold_with_no_further_calls() -> None:
    rec = _Recorder()
    stub = _StubFetcher([_fetch_error() for _ in range(3)])
    ctx = _context(stub, rec, max_consecutive_errors=3)

    async def run():
        for _ in range(2):
            with pytest.raises(FetchError):
                await ctx.fetch(_req())
        with pytest.raises(MaxConsecutiveErrorsExceeded):
            await ctx.fetch(_req())
        # Budget exhausted: further fetch() raises WITHOUT touching transport.
        with pytest.raises(MaxConsecutiveErrorsExceeded):
            await ctx.fetch(_req())

    asyncio.run(run())
    assert stub.calls == 3


# ---------- §17 403/429 precedence ----------

def test_abort_signals_bypass_consecutive_counter() -> None:
    rec = _Recorder()
    abort = HostCircuitOpenError("circuit", attempts=(_attempt(429),))
    stub = _StubFetcher([abort, _ok_response("u")])
    ctx = _context(stub, rec, max_consecutive_errors=3)

    async def run():
        with pytest.raises(HostCircuitOpenError):
            await ctx.fetch(_req())
        assert ctx.consecutive_errors == 0
        await ctx.fetch(_req())
        assert ctx.consecutive_errors == 0

    asyncio.run(run())


# ---------- fetcher per-request ceilings ----------

def test_per_request_retry_ceiling_caps_global_retries() -> None:
    calls: list[httpx.Request] = []
    state = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        state["n"] += 1
        if state["n"] < 2:
            return httpx.Response(500, content=b"err", request=request)
        return httpx.Response(200, content=b"{}", request=request)

    async def run():
        fetcher = HttpFetcher(
            max_retries=5,
            per_domain_min_interval_seconds=0,
            jitter_seconds=0,
            resolve_dns=False,
            transport=httpx.MockTransport(handler),
        )
        async with fetcher:
            response = await fetcher.fetch(
                FetchRequest("https://ceil.example.test/", max_retries=1)
            )
            assert response.status_code == 200
            assert len(calls) == 2  # 1 initial + 1 retry, not 6

    asyncio.run(run())


def test_per_request_retry_ceiling_zero_means_single_attempt() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500, content=b"err", request=request)

    async def run():
        fetcher = HttpFetcher(
            max_retries=5,
            per_domain_min_interval_seconds=0,
            jitter_seconds=0,
            resolve_dns=False,
            transport=httpx.MockTransport(handler),
        )
        async with fetcher:
            with pytest.raises(FetchError):
                await fetcher.fetch(FetchRequest("https://ceil0.example.test/", max_retries=0))

    asyncio.run(run())
    assert len(calls) == 1


def test_per_request_interval_floor_only_adds_spacing() -> None:
    seen: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(asyncio.get_event_loop().time())
        return httpx.Response(200, content=b"{}", request=request)

    async def run():
        fetcher = HttpFetcher(
            max_retries=0,
            per_domain_min_interval_seconds=0,
            jitter_seconds=0,
            resolve_dns=False,
            transport=httpx.MockTransport(handler),
        )
        async with fetcher:
            await fetcher.fetch(FetchRequest("https://floor.example.test/a"))
            await fetcher.fetch(
                FetchRequest("https://floor.example.test/b", min_interval_seconds=0.05)
            )

    asyncio.run(run())
    assert len(seen) == 2
    assert seen[1] - seen[0] >= 0.04


# ---------- §18 interaction + §19 snapshot ----------

def _synthetic_policy_spec(tmp_path: Path) -> dict:
    base = json.loads((DECL_DIR / "specs" / "nvidia.json").read_text(encoding="utf-8"))
    spec = copy.deepcopy(base)
    spec["company"] = {"id": "synpol", "name": "Synthetic Policy Co"}
    spec["safety"] = {
        "sequential_only": True,
        "min_seconds_between_requests": 0.01,
        "long_pause_every_n_requests": 1,
        "long_pause_seconds": 0.02,
        "max_requests_per_run": 2,
        "abort_on_http_403": True,
        "abort_on_http_429": True,
        "max_retries_on_5xx": 0,
        "max_consecutive_errors": 8,
    }
    return spec


def test_interaction_pause_budget_snapshot(tmp_path: Path) -> None:
    """min interval + pause every 1 + budget 2 on a 25-job catalog:
    exactly 2 requests, 1 pause, 20 partial jobs, complete=false."""
    import httpx as _httpx

    from research_agent.sources.base import PortalScanContext as Ctx
    from research_agent.sources.declarative.adapter import (
        DeclarativeSourceAdapter,
        DeclarativeSourceBinding,
    )
    from research_agent.sources.base import PortalTarget

    spec = _synthetic_policy_spec(tmp_path)
    spec_path = tmp_path / "polspec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    adapter = DeclarativeSourceAdapter(
        [DeclarativeSourceBinding("https://pol.example.test/jobs", "polspec.json")],
        base_dir=tmp_path,
    )

    calls: list[_httpx.Request] = []
    pauses: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        pauses.append(seconds)

    def _item(i: int) -> dict:
        return {
            "id": f"S-{i:05d}",
            "displayJobId": f"D-{i:05d}",
            "name": f"Role {i}",
            "department": "Engineering",
            "postedTs": 1756684800,
            "locations": ["Nowhere"],
            "publicUrl": f"https://pol.example.test/j/S-{i:05d}",
        }

    def handler(request: _httpx.Request) -> _httpx.Response:
        calls.append(request)
        start = int(dict(_httpx.QueryParams(request.url.query)).get("start", 0))
        items = [_item(i) for i in range(start, min(start + 10, 25))]
        return _httpx.Response(
            200, json={"data": {"positions": items, "count": 25}}, request=request
        )

    async def run():
        fetcher = HttpFetcher(
            max_retries=0,
            per_domain_min_interval_seconds=0,
            jitter_seconds=0,
            resolve_dns=False,
            transport=_httpx.MockTransport(handler),
        )
        async with fetcher:
            context = Ctx(
                fetcher=fetcher,
                max_pages_per_portal=30,
                max_jobs_per_portal=500,
                sleep=fake_sleep,
            )
            target = PortalTarget(
                portal_id=1,
                jobs_search_url="https://pol.example.test/jobs",
                normalized_jobs_url="https://pol.example.test/jobs",
                host="pol.example.test",
                ats_families=(),
                ats_confidences=(),
            )
            return await adapter.scan(target, context)

    result = asyncio.run(run())
    assert len(calls) == 2
    assert pauses == [0.02]
    assert len(result.jobs) == 20
    assert result.is_complete_snapshot is False
    assert any("budget" in warning for warning in result.warnings)


def test_request_budget_counts_retries_as_wire_attempts() -> None:
    """max_requests=2 with a retryable-then-failing page: the retry consumes
    the budget, so the second page never starts."""
    rec = _Recorder()
    err = FetchError("down", attempts=(_attempt(500), _attempt(500)))
    stub = _StubFetcher([err, _ok_response("u")])
    ctx = _context(stub, rec, max_requests=2)

    async def run():
        with pytest.raises(FetchError):
            await ctx.fetch(_req())
        assert ctx.wire_attempts == 2
        with pytest.raises(ScanRequestBudgetExceeded):
            await ctx.fetch(_req())

    asyncio.run(run())
    assert stub.calls == 1
