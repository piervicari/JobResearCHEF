"""Wire-exact safety policy tests (offline, deterministic).

Hard wire-attempt cap and wire-based periodic pauses are enforced by
HttpFetcher at the real outbound attempt point, driven by the per-scan
ScanWirePolicy. Transports are httpx.MockTransport or in-memory stubs;
clocks/sleeps are fake. Zero network.
"""
from __future__ import annotations

import asyncio
import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from research_agent.pipeline.cache import FileResponseCache
from research_agent.pipeline.http import (
    FetchAttempt,
    FetchError,
    FetchRequest,
    FetchResponse,
    HostCircuitOpenError,
    HttpFetcher,
    RequestBudgetExceededError,
    ScanWirePolicy,
)
from research_agent.sources.base import (
    MaxConsecutiveErrorsExceeded,
    PortalScanContext,
    ScanRequestBudgetExceeded,
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
    """In-memory fetcher for LOGICAL-failure tests (consecutive budget).

    Never sees wire policies — used only where the real fetcher is not
    under test. Explodes when exhausted (no requests after stop).
    """

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


class _EventLog:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def sleep(self, seconds: float) -> None:
        self.events.append(f"P:{seconds:g}")

    def wire(self) -> None:
        self.events.append("R")


def _fetcher(
    handler: object,
    cache: FileResponseCache | None = None,
    max_retries: int = 0,
) -> HttpFetcher:
    return HttpFetcher(
        max_retries=max_retries,
        per_domain_min_interval_seconds=0,
        jitter_seconds=0,
        resolve_dns=False,
        transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
        cache=cache,
    )


def _policy_request(url: str, policy: ScanWirePolicy) -> FetchRequest:
    return FetchRequest(url, wire_policy=policy)


# ---------- §17 hard cap ----------

def test_hard_cap_budget_1_single_200() -> None:
    """Test A: budget=1, one 200 → exactly 1 wire attempt, PASS."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, content=b"{}", request=request)

    policy = ScanWirePolicy(max_wire_attempts=1)
    async def run():
        fetcher = _fetcher(handler)
        async with fetcher:
            response = await fetcher.fetch(_policy_request("https://a.example.test/", policy))
        return response

    response = asyncio.run(run())
    assert response.status_code == 200
    assert len(calls) == 1
    assert policy.used_wire_attempts == 1  # noqa: F821


def test_hard_cap_budget_1_blocks_retry() -> None:
    """Test B: budget=1, 500 then 200, max_retries=1 → only the 500 runs."""
    calls: list[httpx.Request] = []
    state = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        state["n"] += 1
        if state["n"] < 2:
            return httpx.Response(500, content=b"err", request=request)
        return httpx.Response(200, content=b"{}", request=request)

    policy = ScanWirePolicy(max_wire_attempts=1)
    async def run():
        fetcher = _fetcher(handler, max_retries=1)
        async with fetcher:
            with pytest.raises(FetchError):
                await fetcher.fetch(
                    FetchRequest("https://b.example.test/", max_retries=1, wire_policy=policy)
                )

    asyncio.run(run())
    assert len(calls) == 1
    assert policy.used_wire_attempts == 1  # noqa: F821


def test_hard_cap_budget_2_allows_one_retry() -> None:
    """Test C: budget=2, 500 then 200 → 2 wire attempts, PASS."""
    calls: list[httpx.Request] = []
    state = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        state["n"] += 1
        if state["n"] < 2:
            return httpx.Response(500, content=b"err", request=request)
        return httpx.Response(200, content=b"{}", request=request)

    policy = ScanWirePolicy(max_wire_attempts=2)
    async def run():
        fetcher = _fetcher(handler, max_retries=1)
        async with fetcher:
            response = await fetcher.fetch(
                FetchRequest("https://c.example.test/", max_retries=1, wire_policy=policy)
            )
        return response

    response = asyncio.run(run())
    assert response.status_code == 200
    assert len(calls) == 2


def test_hard_cap_budget_1_blocks_redirect_follow() -> None:
    """Test D: budget=1, 302 → target: only the first request runs, the
    redirect is NOT followed (that would be wire attempt #2)."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/start":
            return httpx.Response(
                302, headers={"Location": "/target"}, content=b"", request=request
            )
        return httpx.Response(200, content=b"{}", request=request)

    policy = ScanWirePolicy(max_wire_attempts=1)
    async def run():
        fetcher = _fetcher(handler)
        async with fetcher:
            with pytest.raises(RequestBudgetExceededError):
                await fetcher.fetch(
                    _policy_request("https://d.example.test/start", policy)
                )

    asyncio.run(run())
    assert len(calls) == 1


def test_hard_cap_used_9_of_10_then_500() -> None:
    """Test E: used=9, budget=10, next wire returns 500 with max_retries=1
    → total stays 10, NO wire #11."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500, content=b"err", request=request)

    policy = ScanWirePolicy(max_wire_attempts=10)
    async def run():
        fetcher = _fetcher(handler, max_retries=1)
        policy.used_wire_attempts = 9  # as if a previous page consumed 9
        async with fetcher:
            with pytest.raises(FetchError):
                await fetcher.fetch(
                    FetchRequest("https://e.example.test/", max_retries=1, wire_policy=policy)
                )

    asyncio.run(run())
    assert len(calls) == 1
    assert policy.used_wire_attempts == 10  # noqa: F821


# ---------- §18 wire-based periodic pause ----------

def test_pause_four_wires_n3() -> None:
    log = _EventLog()

    def handler(request: httpx.Request) -> httpx.Response:
        log.wire()
        return httpx.Response(200, content=b"{}", request=request)

    policy = ScanWirePolicy(
        max_wire_attempts=10, pause_every_n_attempts=3, pause_seconds=5.0,
        sleep=log.sleep,
    )
    async def run():
        fetcher = _fetcher(handler)
        async with fetcher:
            for i in range(4):
                await fetcher.fetch(_policy_request(f"https://p.example.test/{i}", policy))

    asyncio.run(run())
    assert log.events == ["R", "R", "R", "P:5", "R"]


def test_pause_exact_boundary_has_no_trailing_pause() -> None:
    log = _EventLog()

    def handler(request: httpx.Request) -> httpx.Response:
        log.wire()
        return httpx.Response(200, content=b"{}", request=request)

    policy = ScanWirePolicy(
        max_wire_attempts=10, pause_every_n_attempts=3, pause_seconds=5.0,
        sleep=log.sleep,
    )
    async def run():
        fetcher = _fetcher(handler)
        async with fetcher:
            for i in range(3):
                await fetcher.fetch(_policy_request(f"https://p.example.test/{i}", policy))

    asyncio.run(run())
    assert log.events == ["R", "R", "R"]


def test_pause_retry_shifts_pause() -> None:
    """§8 critical: fetch#1 = 500 + retry 200 (2 wires), fetch#2 = 200
    (wire 3) → pause BEFORE the next wire of fetch#3."""
    log = _EventLog()
    state = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        log.wire()
        state["n"] += 1
        if state["n"] == 1:
            return httpx.Response(500, content=b"err", request=request)
        return httpx.Response(200, content=b"{}", request=request)

    policy = ScanWirePolicy(
        max_wire_attempts=10, pause_every_n_attempts=3, pause_seconds=5.0,
        sleep=log.sleep,
    )
    async def run():
        fetcher = _fetcher(handler, max_retries=1)
        async with fetcher:
            await fetcher.fetch(
                FetchRequest("https://r.example.test/1", max_retries=1, wire_policy=policy)
            )
            await fetcher.fetch(_policy_request("https://r.example.test/2", policy))
            await fetcher.fetch(_policy_request("https://r.example.test/3", policy))

    asyncio.run(run())
    assert log.events == ["R", "R", "R", "P:5", "R"]


def test_pause_redirect_counts() -> None:
    """Redirect follow-up is wire #2; next request is wire #3; the request
    after that pauses."""
    log = _EventLog()

    def handler(request: httpx.Request) -> httpx.Response:
        log.wire()
        if request.url.path == "/a":
            return httpx.Response(
                302, headers={"Location": "/b"}, content=b"", request=request
            )
        return httpx.Response(200, content=b"{}", request=request)

    policy = ScanWirePolicy(
        max_wire_attempts=10, pause_every_n_attempts=3, pause_seconds=5.0,
        sleep=log.sleep,
    )
    async def run():
        fetcher = _fetcher(handler)
        async with fetcher:
            await fetcher.fetch(_policy_request("https://x.example.test/a", policy))
            await fetcher.fetch(_policy_request("https://x.example.test/c", policy))
            await fetcher.fetch(_policy_request("https://x.example.test/d", policy))

    asyncio.run(run())
    assert log.events == ["R", "R", "R", "P:5", "R"]
    assert policy.used_wire_attempts == 4  # noqa: F821


def test_pause_seven_wires() -> None:
    log = _EventLog()

    def handler(request: httpx.Request) -> httpx.Response:
        log.wire()
        return httpx.Response(200, content=b"{}", request=request)

    policy = ScanWirePolicy(
        max_wire_attempts=10, pause_every_n_attempts=3, pause_seconds=5.0,
        sleep=log.sleep,
    )
    async def run():
        fetcher = _fetcher(handler)
        async with fetcher:
            for i in range(7):
                await fetcher.fetch(_policy_request(f"https://p.example.test/{i}", policy))

    asyncio.run(run())
    assert log.events == ["R"] * 3 + ["P:5"] + ["R"] * 3 + ["P:5", "R"]


# ---------- §16 cache: conditional requests still touch the network ----------

def test_cache_conditional_request_consumes_wire_attempt(tmp_path: Path) -> None:
    """No zero-wire cache path exists: a 304 conditional still performs one
    outbound attempt and consumes budget exactly once."""
    calls: list[httpx.Request] = []
    state = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        state["n"] += 1
        if state["n"] == 1:
            return httpx.Response(
                200, content=b'{"a":1}', headers={"ETag": '"v1"'}, request=request
            )
        assert request.headers.get("if-none-match") == '"v1"'
        return httpx.Response(304, content=b"", request=request)

    policy = ScanWirePolicy(max_wire_attempts=10)
    async def run():
        cache = FileResponseCache(tmp_path / "cache")
        fetcher = _fetcher(handler, cache=cache)
        async with fetcher:
            first = await fetcher.fetch(
                _policy_request("https://cache.example.test/data", policy)
            )
            second = await fetcher.fetch(
                _policy_request("https://cache.example.test/data", policy)
            )
        return first, second

    first, second = asyncio.run(run())
    assert first.status_code == 200 and not first.from_cache
    assert second.from_cache and second.status_code == 200
    assert len(calls) == 2
    assert policy.used_wire_attempts == 2  # noqa: F821


# ---------- consecutive budget (logical, unchanged) + terminal budget ----------

def _fetch_error() -> FetchError:
    return FetchError("boom", attempts=(_attempt(None),))


def _stub_context(stub, **policy) -> PortalScanContext:
    ctx = PortalScanContext(fetcher=stub, max_pages_per_portal=30, max_jobs_per_portal=500)  # type: ignore[arg-type]
    ctx.configure_scan_limits(**policy)
    return ctx


def test_consecutive_errors_reset_on_success() -> None:
    stub = _StubFetcher(
        [_fetch_error(), _fetch_error(), _ok_response("u"), _fetch_error(), _fetch_error()]
    )
    ctx = _stub_context(stub, max_consecutive_errors=3)

    async def run():
        for _ in range(2):
            with pytest.raises(FetchError):
                await ctx.fetch(FetchRequest("https://u.example.test/"))
        await ctx.fetch(FetchRequest("https://u.example.test/"))
        for _ in range(2):
            with pytest.raises(FetchError):
                await ctx.fetch(FetchRequest("https://u.example.test/"))

    asyncio.run(run())  # threshold 3 never reached consecutively
    assert stub.calls == 5


def test_consecutive_errors_stop_at_threshold_with_no_further_calls() -> None:
    stub = _StubFetcher([_fetch_error() for _ in range(3)])
    ctx = _stub_context(stub, max_consecutive_errors=3)

    async def run():
        for _ in range(2):
            with pytest.raises(FetchError):
                await ctx.fetch(FetchRequest("https://u.example.test/"))
        with pytest.raises(MaxConsecutiveErrorsExceeded):
            await ctx.fetch(FetchRequest("https://u.example.test/"))
        with pytest.raises(MaxConsecutiveErrorsExceeded):
            await ctx.fetch(FetchRequest("https://u.example.test/"))

    asyncio.run(run())
    assert stub.calls == 3


def test_abort_signals_bypass_consecutive_counter() -> None:
    abort = HostCircuitOpenError("circuit", attempts=(_attempt(429),))
    stub = _StubFetcher([abort, _ok_response("u")])
    ctx = _stub_context(stub, max_consecutive_errors=3)

    async def run():
        with pytest.raises(HostCircuitOpenError):
            await ctx.fetch(FetchRequest("https://u.example.test/"))
        assert ctx.consecutive_errors == 0
        await ctx.fetch(FetchRequest("https://u.example.test/"))
        assert ctx.consecutive_errors == 0

    asyncio.run(run())


def test_context_precheck_raises_without_fetch_when_exhausted() -> None:
    """remaining<=0 → ScanRequestBudgetExceeded with zero fetch, zero wire."""
    stub = _StubFetcher([_ok_response("u")])
    ctx = _stub_context(stub, max_requests=1)
    ctx.wire_policy.used_wire_attempts = 1  # type: ignore[union-attr]

    async def run():
        with pytest.raises(ScanRequestBudgetExceeded):
            await ctx.fetch(FetchRequest("https://u.example.test/"))

    asyncio.run(run())
    assert stub.calls == 0


# ---------- fetcher per-request ceilings (unchanged behavior) ----------

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
        fetcher = _fetcher(handler, max_retries=1)
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
        fetcher = _fetcher(handler)
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
        fetcher = _fetcher(handler)
        async with fetcher:
            await fetcher.fetch(FetchRequest("https://floor.example.test/a"))
            await fetcher.fetch(
                FetchRequest("https://floor.example.test/b", min_interval_seconds=0.05)
            )

    asyncio.run(run())
    assert len(seen) == 2
    assert seen[1] - seen[0] >= 0.04


# ---------- §19 legacy regression: no policy → identical path ----------

def test_legacy_request_without_policy_has_no_pause_no_cap() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, content=b"{}", request=request)

    async def run():
        fetcher = _fetcher(handler)
        async with fetcher:
            for i in range(4):
                request = FetchRequest(f"https://leg.example.test/{i}")
                assert request.wire_policy is None
                await fetcher.fetch(request)

    asyncio.run(run())
    assert len(calls) == 4


# ---------- adapter-level: interaction + terminal budget (§13/§14/§18) ----------

def _eightfold_synthetic_adapter(tmp_path: Path, safety: dict):
    from research_agent.sources.base import PortalTarget
    from research_agent.sources.declarative.adapter import (
        DeclarativeSourceAdapter,
        DeclarativeSourceBinding,
    )

    decl = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "research_agent"
        / "sources"
        / "declarative"
    )
    base = json.loads((decl / "specs" / "nvidia.json").read_text(encoding="utf-8"))
    spec = copy.deepcopy(base)
    spec["company"] = {"id": "synpol", "name": "Synthetic Policy Co"}
    spec["safety"] = safety
    (tmp_path / "polspec.json").write_text(json.dumps(spec), encoding="utf-8")
    adapter = DeclarativeSourceAdapter(
        [DeclarativeSourceBinding("https://pol.example.test/jobs", "polspec.json")],
        base_dir=tmp_path,
    )
    target = PortalTarget(
        portal_id=1,
        jobs_search_url="https://pol.example.test/jobs",
        normalized_jobs_url="https://pol.example.test/jobs",
        host="pol.example.test",
        ats_families=(),
        ats_confidences=(),
    )
    return adapter, target


def _pages_handler(calls: list, total: int, *, fail_on: set[int] | None = None):
    fail_on = fail_on or set()

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        start = int(dict(httpx.QueryParams(request.url.query)).get("start", 0))
        if start in fail_on:
            return httpx.Response(500, content=b"err", request=request)
        items = [
            {
                "id": f"S-{i:05d}",
                "displayJobId": f"D-{i:05d}",
                "name": f"Role {i}",
                "department": "Engineering",
                "postedTs": 1756684800,
                "locations": ["Nowhere"],
                "publicUrl": f"https://pol.example.test/j/S-{i:05d}",
            }
            for i in range(start, min(start + 10, total))
        ]
        return httpx.Response(
            200, json={"data": {"positions": items, "count": total}}, request=request
        )

    return handler


def test_adapter_interaction_pause_budget_snapshot(tmp_path: Path) -> None:
    """Spec: interval floor + pause every 1 wire + budget 2 wires on a
    25-job catalog → exactly 2 wire attempts, one real pause, 20 partial
    jobs, complete_snapshot=false, explicit warning."""
    import time as _time

    from research_agent.sources.base import PortalScanContext as _Ctx

    adapter, target = _eightfold_synthetic_adapter(
        tmp_path,
        {
            "sequential_only": True,
            "min_seconds_between_requests": 0.01,
            "long_pause_every_n_requests": 1,
            "long_pause_seconds": 0.05,
            "max_requests_per_run": 2,
            "abort_on_http_403": True,
            "abort_on_http_429": True,
            "max_retries_on_5xx": 0,
            "max_consecutive_errors": 8,
        },
    )
    calls: list[httpx.Request] = []

    async def run():
        fetcher = _fetcher(_pages_handler(calls, 25))
        async with fetcher:
            context = _Ctx(fetcher=fetcher, max_pages_per_portal=30, max_jobs_per_portal=500)
            started = _time.monotonic()
            result = await adapter.scan(target, context)
            return result, _time.monotonic() - started, context

    result, elapsed, context = asyncio.run(run())
    assert len(calls) == 2
    assert elapsed >= 0.04  # the wire-based pause really slept
    assert len(result.jobs) == 20
    assert result.is_complete_snapshot is False
    assert any("budget" in warning for warning in result.warnings)
    assert context.wire_policy is not None
    assert context.wire_policy.used_wire_attempts == 2


def test_adapter_global_host_budget_exhaustion_is_terminal(tmp_path: Path) -> None:
    """§14: fetcher per-host budget 1 exhausted on page 2 → terminal stop,
    NO same-offset retry, partial page 1 kept, complete=false."""
    from research_agent.sources.base import PortalScanContext as _Ctx

    adapter, target = _eightfold_synthetic_adapter(
        tmp_path,
        {
            "sequential_only": True,
            "min_seconds_between_requests": 0,
            "long_pause_every_n_requests": 0,
            "long_pause_seconds": 0,
            "max_requests_per_run": 600,
            "abort_on_http_403": True,
            "abort_on_http_429": True,
            "max_retries_on_5xx": 0,
            "max_consecutive_errors": 8,
        },
    )
    calls: list[httpx.Request] = []

    async def run():
        fetcher = HttpFetcher(
            max_retries=0,
            per_domain_min_interval_seconds=0,
            jitter_seconds=0,
            resolve_dns=False,
            max_requests_per_host_per_run=1,
            transport=httpx.MockTransport(_pages_handler(calls, 25)),
        )
        async with fetcher:
            context = _Ctx(fetcher=fetcher, max_pages_per_portal=30, max_jobs_per_portal=500)
            return await adapter.scan(target, context)

    result = asyncio.run(run())
    assert len(calls) == 1  # page 2 never requested, let alone retried
    assert len(result.jobs) == 10
    assert result.is_complete_snapshot is False
    assert any("budget" in warning for warning in result.warnings)
