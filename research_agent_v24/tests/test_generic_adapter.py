import asyncio
from pathlib import Path

import httpx
import pytest

from research_agent.pipeline.http import HttpFetcher
from research_agent.sources.base import PortalScanContext, PortalTarget
from research_agent.sources.official.generic import (
    GenericOfficialHtmlAdapter,
    RobotsDisallowed,
)


def _target(path: str = "/careers") -> PortalTarget:
    return PortalTarget(
        portal_id=1,
        jobs_search_url=f"https://careers.example.test{path}",
        normalized_jobs_url=f"https://careers.example.test{path}",
        host="careers.example.test",
        ats_families=("Custom / backend unverified",),
        ats_confidences=("High",),
    )


def _run_adapter(handler: object, target: PortalTarget) -> tuple[object, list[str]]:
    requested: list[str] = []

    def recording_handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return handler(request)

    async def run():
        fetcher = HttpFetcher(
            max_retries=0,
            per_domain_min_interval_seconds=0,
            jitter_seconds=0,
            resolve_dns=False,
            transport=httpx.MockTransport(recording_handler),
        )
        async with fetcher:
            return await GenericOfficialHtmlAdapter().scan(target, PortalScanContext(fetcher))

    return asyncio.run(run()), requested


def test_generic_adapter_enforces_robots_and_parses_json_ld() -> None:
    html = (Path(__file__).parent / "fixtures" / "generic_job_page.html").read_text(
        encoding="utf-8"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private\n", request=request)
        return httpx.Response(
            200, text=html, headers={"Content-Type": "text/html"}, request=request
        )

    result, requested = _run_adapter(handler, _target())
    assert requested == [
        "https://careers.example.test/robots.txt",
        "https://careers.example.test/careers",
    ]
    assert len(result.jobs) == 1
    job = result.jobs[0]
    assert job.source_job_id == "GEN-101"
    assert job.title == "Cybersecurity Graduate"
    assert job.company == "Example Ltd"
    assert job.country == "IT"
    assert job.city == "Rome"


def test_generic_adapter_stops_when_robots_disallows_path() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="User-agent: *\nDisallow: /private\n", request=request)

    with pytest.raises(RobotsDisallowed):
        _run_adapter(handler, _target("/private/jobs"))


def test_generic_adapter_allows_missing_robots_and_discovers_job_anchors() -> None:
    html = """
    <html><body>
      <a href>Malformed link without a URL</a>
      <a href="/job/123/security-intern">Security Intern</a>
      <a href="/about">About us</a>
      <a href="/job/123/security-intern">View job</a>
    </body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404, request=request)
        return httpx.Response(
            200, text=html, headers={"Content-Type": "text/html"}, request=request
        )

    result, _ = _run_adapter(handler, _target())
    assert len(result.jobs) == 1
    assert result.jobs[0].title == "Security Intern"
    assert result.warnings == ("anchor discovery only; details require targeted enrichment",)


def test_generic_adapter_rejects_navigation_find_jobs_as_vacancy() -> None:
    html = """
    <html><body>
      <a href="/jobs/">Find Jobs</a>
      <a href="/jobs/123/security-engineer">Security Engineer</a>
    </body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404, request=request)
        return httpx.Response(
            200, text=html, headers={"Content-Type": "text/html"}, request=request
        )

    result, _ = _run_adapter(handler, _target())
    assert [job.title for job in result.jobs] == ["Security Engineer"]
