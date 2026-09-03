import asyncio

import httpx
import pytest

from research_agent.pipeline.http import (
    AccessChallengeError,
    FetchRequest,
    HostCircuitOpenError,
    HttpFetcher,
    RequestBudgetExceededError,
    ResponseTooLargeError,
    UnsafeDestinationError,
)


def test_fetcher_rejects_literal_private_destination_before_network() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, text="unexpected", request=request)

    async def run() -> None:
        fetcher = HttpFetcher(
            max_retries=0,
            resolve_dns=False,
            transport=httpx.MockTransport(handler),
        )
        async with fetcher:
            with pytest.raises(UnsafeDestinationError, match="Non-public"):
                await fetcher.fetch(FetchRequest("http://127.0.0.1/admin"))

    asyncio.run(run())
    assert calls == 0


def test_fetcher_revalidates_redirect_and_blocks_private_target() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(
            302,
            headers={"Location": "https://169.254.169.254/"},
            request=request,
        )

    async def run() -> None:
        fetcher = HttpFetcher(
            max_retries=0,
            resolve_dns=False,
            transport=httpx.MockTransport(handler),
        )
        async with fetcher:
            with pytest.raises(UnsafeDestinationError, match="Non-public"):
                await fetcher.fetch(FetchRequest("https://jobs.example.test/openings"))

    asyncio.run(run())
    assert requested == ["https://jobs.example.test/openings"]


def test_fetcher_follows_public_redirect_with_per_request_audit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "jobs.example.test":
            return httpx.Response(
                302,
                headers={"Location": "https://api.example.test/jobs"},
                request=request,
            )
        return httpx.Response(200, json={"jobs": []}, request=request)

    async def run() -> None:
        fetcher = HttpFetcher(
            max_retries=0,
            resolve_dns=False,
            transport=httpx.MockTransport(handler),
        )
        async with fetcher:
            response = await fetcher.fetch(
                FetchRequest("https://jobs.example.test/openings")
            )
        assert response.final_url == "https://api.example.test/jobs"
        assert [attempt.status_code for attempt in response.attempts] == [302, 200]
        assert [attempt.redirect for attempt in response.attempts] == [True, False]

    asyncio.run(run())


def test_fetcher_stops_oversized_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"123456", request=request)

    async def run() -> None:
        fetcher = HttpFetcher(
            max_retries=0,
            max_response_bytes=5,
            resolve_dns=False,
            transport=httpx.MockTransport(handler),
        )
        async with fetcher:
            with pytest.raises(ResponseTooLargeError, match="exceeds 5 bytes"):
                await fetcher.fetch(FetchRequest("https://jobs.example.test/openings"))

    asyncio.run(run())


def test_first_429_opens_circuit_without_retrying() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, headers={"Retry-After": "999"}, request=request)

    async def run() -> None:
        fetcher = HttpFetcher(
            max_retries=2,
            per_domain_min_interval_seconds=0,
            jitter_seconds=0,
            resolve_dns=False,
            transport=httpx.MockTransport(handler),
        )
        async with fetcher:
            with pytest.raises(HostCircuitOpenError):
                await fetcher.fetch(FetchRequest("https://jobs.example.test/openings"))

    asyncio.run(run())
    assert calls == 1


def test_host_circuit_blocks_later_requests_after_403() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(403, text="denied", request=request)

    async def run() -> None:
        fetcher = HttpFetcher(
            max_retries=0,
            per_domain_min_interval_seconds=0,
            jitter_seconds=0,
            resolve_dns=False,
            transport=httpx.MockTransport(handler),
        )
        async with fetcher:
            first = await fetcher.fetch(FetchRequest("https://jobs.example.test/one"))
            assert first.status_code == 403
            with pytest.raises(HostCircuitOpenError, match="HTTP 403"):
                await fetcher.fetch(FetchRequest("https://jobs.example.test/two"))

    asyncio.run(run())
    assert calls == 1


def test_fetcher_enforces_host_and_overall_request_budgets() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, text="ok", request=request)

    async def run() -> None:
        fetcher = HttpFetcher(
            max_retries=0,
            max_requests_per_host_per_run=2,
            max_requests_per_run=2,
            per_domain_min_interval_seconds=0,
            jitter_seconds=0,
            resolve_dns=False,
            transport=httpx.MockTransport(handler),
        )
        async with fetcher:
            await fetcher.fetch(FetchRequest("https://jobs.example.test/one"))
            await fetcher.fetch(FetchRequest("https://jobs.example.test/two"))
            with pytest.raises(RequestBudgetExceededError, match="Per-host"):
                await fetcher.fetch(FetchRequest("https://jobs.example.test/three"))

    asyncio.run(run())
    assert calls == 2


def test_fetcher_detects_strong_access_challenge() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text="<html><title>Just a moment...</title><div>Verify you are human</div></html>",
            request=request,
        )

    async def run() -> None:
        fetcher = HttpFetcher(
            max_retries=0,
            per_domain_min_interval_seconds=0,
            jitter_seconds=0,
            resolve_dns=False,
            transport=httpx.MockTransport(handler),
        )
        async with fetcher:
            with pytest.raises(AccessChallengeError):
                await fetcher.fetch(FetchRequest("https://jobs.example.test/openings"))

    asyncio.run(run())


def test_fetcher_detects_known_challenge_redirect_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "jobs.example.test":
            return httpx.Response(
                302,
                headers={"Location": "https://validate.perfdrive.com/check"},
                request=request,
            )
        return httpx.Response(200, text="validation required", request=request)

    async def run() -> None:
        fetcher = HttpFetcher(
            max_retries=0,
            per_domain_min_interval_seconds=0,
            jitter_seconds=0,
            resolve_dns=False,
            transport=httpx.MockTransport(handler),
        )
        async with fetcher:
            with pytest.raises(AccessChallengeError, match="known challenge endpoint"):
                await fetcher.fetch(FetchRequest("https://jobs.example.test/openings"))

    asyncio.run(run())
