import asyncio
import json
from urllib.parse import parse_qs

import httpx

from research_agent.pipeline.http import HttpFetcher
from research_agent.sources.ats.google_careers import GoogleCareersAdapter
from research_agent.sources.base import PortalScanContext, PortalTarget


def _target() -> PortalTarget:
    return PortalTarget(
        portal_id=1,
        jobs_search_url="https://www.google.com/about/careers/applications/jobs/results",
        normalized_jobs_url="https://www.google.com/about/careers/applications/jobs/results",
        host="www.google.com",
        ats_families=("Custom Google Careers",),
        ats_confidences=("Verified",),
    )


def _job(job_id: int) -> list[object]:
    row: list[object] = [None] * 21
    row[0] = str(job_id)
    row[1] = f"Security Engineer {job_id}"
    row[2] = f"https://www.google.com/about/careers/applications/jobs/results/{job_id}"
    row[3] = [None, "<ul><li>Investigate security incidents</li></ul>"]
    row[4] = [None, "<ul><li>Security engineering experience</li></ul>"]
    row[7] = "Google"
    row[9] = [["Zurich, Switzerland", ["Zurich, Switzerland"], "Zurich", None, "ZH", "CH"]]
    row[10] = [None, "<p>Protect Google systems and users.</p>"]
    row[12] = [1_787_000_000 + job_id, 0]
    row[13] = [1_787_100_000 + job_id, 0]
    row[19] = [None, "<ul><li>Bachelor's degree or equivalent experience</li></ul>"]
    return row


def _rpc_response(jobs: list[list[object]], total: int) -> str:
    payload = json.dumps([jobs, None, total], separators=(",", ":"))
    envelope = json.dumps([["wrb.fr", "r06xKb", payload, None, None, None, "generic"]])
    return ")]}'\n123\n" + envelope + "\n"


def test_google_careers_adapter_pages_structured_rpc_and_returns_complete_catalog() -> None:
    seen_pages: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path.endswith("/HiringCportalFrontendUi/data/batchexecute")
        form = parse_qs(request.content.decode())
        outer = json.loads(form["f.req"][0])
        assert outer[0][0][0] == "r06xKb"
        args = json.loads(outer[0][0][1])
        page = args[0][7]
        seen_pages.append(page)
        jobs = [_job(i) for i in range(1, 21)] if page == 1 else [_job(21)]
        return httpx.Response(
            200,
            text=_rpc_response(jobs, 21),
            headers={"Content-Type": "application/json; charset=utf-8"},
            request=request,
        )

    async def run():
        fetcher = HttpFetcher(
            max_retries=0,
            per_domain_min_interval_seconds=0,
            jitter_seconds=0,
            resolve_dns=False,
            transport=httpx.MockTransport(handler),
        )
        async with fetcher:
            context = PortalScanContext(fetcher=fetcher, max_pages_per_portal=5, max_jobs_per_portal=100)
            return await GoogleCareersAdapter().scan(_target(), context)

    result = asyncio.run(run())
    assert seen_pages == [1, 2]
    assert result.is_complete_snapshot is True
    assert len(result.jobs) == 21
    first = result.jobs[0]
    assert first.source == "google_careers_rpc"
    assert first.source_job_id == "1"
    assert first.title == "Security Engineer 1"
    assert first.company == "Google"
    assert first.location == "Zurich, Switzerland"
    assert first.city == "Zurich"
    assert first.country == "CH"
    assert "Protect Google systems" in first.description
    assert "Investigate security incidents" in first.description
    assert first.posted_at is not None


def test_google_careers_adapter_marks_page_limited_scan_incomplete() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_rpc_response([_job(i) for i in range(1, 21)], 45), request=request)

    async def run():
        fetcher = HttpFetcher(
            max_retries=0,
            per_domain_min_interval_seconds=0,
            jitter_seconds=0,
            resolve_dns=False,
            transport=httpx.MockTransport(handler),
        )
        async with fetcher:
            context = PortalScanContext(fetcher=fetcher, max_pages_per_portal=1, max_jobs_per_portal=100)
            return await GoogleCareersAdapter().scan(_target(), context)

    result = asyncio.run(run())
    assert result.is_complete_snapshot is False
    assert len(result.jobs) == 20
    assert any("snapshot incomplete" in warning for warning in result.warnings)


def test_google_careers_adapter_requires_platform_signature_not_company_id() -> None:
    adapter = GoogleCareersAdapter()
    assert adapter.supports(_target()) is True
    wrong_family = PortalTarget(
        **{**_target().__dict__, "ats_families": ("Unknown",)}
    )
    assert adapter.supports(wrong_family) is False
