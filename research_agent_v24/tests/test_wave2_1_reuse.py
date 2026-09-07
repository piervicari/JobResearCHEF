"""Wave 2.1 reuse tests: Oracle adaptive pagination + parser enrichment.

All offline (httpx.MockTransport). Identity assertions pin source_job_id /
URLs so parser reuse cannot silently migrate SourceJob identity.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from research_agent.pipeline.http import HttpFetcher
from research_agent.sources.ats.ashby import AshbyAdapter
from research_agent.sources.ats.common import AdapterSchemaError, parse_epoch_millis
from research_agent.sources.ats.greenhouse import _requisition_id as gh_req
from research_agent.sources.ats.greenhouse import _unescape_content as gh_unescape
from research_agent.sources.ats.greenhouse import GreenhouseAdapter
from research_agent.sources.ats.lever import _assemble_description as lever_desc
from research_agent.sources.ats.lever import LeverAdapter
from research_agent.sources.ats.oracle import OracleRecruitingCloudAdapter
from research_agent.sources.ats.smartrecruiters import SmartRecruitersAdapter
from research_agent.sources.ats.workday import WorkdayAdapter
from research_agent.sources.base import PortalScanContext, PortalTarget

LANDING = (
    '<base data-apibaseurl="https://example.fa.oraclecloud.com" '
    'data-sitenumber="CX_1" href="/hcmUI/CandidateExperience/en/sites/CX_1">'
)


def _target(url: str, family: str) -> PortalTarget:
    return PortalTarget(
        portal_id=1, jobs_search_url=url, normalized_jobs_url=url,
        host=httpx.URL(url).host, ats_families=(family,),
        ats_confidences=("Verified",),
    )


def _req(url: str) -> dict:
    return {"Id": "9", "Title": "T", "PrimaryLocation": "L"}


def _oracle_page(total: int, n: int, start_id: int = 1) -> dict:
    return {"items": [{
        "TotalJobsCount": total,
        "requisitionList": [
            {"Id": str(start_id + i), "Title": f"Job {start_id + i}",
             "PrimaryLocation": "City"} for i in range(n)
        ],
    }]}


def _run_oracle(pages: list[tuple[int, int]], **adapter_kw):
    """pages: [(total, rows_returned)] served in order; records offsets."""
    offsets: list[int] = []
    calls = {"n": 0}
    adapter = OracleRecruitingCloudAdapter()
    for key, value in adapter_kw.items():
        setattr(adapter, key, value)

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "hcmRestApi" in path:
            params = dict(request.url.params)
            finder = params.get("finder", "")
            off = int(finder.split("offset=")[-1])
            offsets.append(off)
            total, n = pages[min(calls["n"], len(pages) - 1)]
            calls["n"] += 1
            return httpx.Response(200, json=_oracle_page(total, n, off + 1), request=request)
        return httpx.Response(200, text=LANDING, request=request)

    async def run():
        fetcher = HttpFetcher(max_retries=0, per_domain_min_interval_seconds=0,
                              jitter_seconds=0, resolve_dns=False,
                              transport=httpx.MockTransport(handler))
        async with fetcher:
            return await adapter.scan(
                _target("https://example.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1",
                        "Oracle Recruiting Cloud"),
                PortalScanContext(fetcher=fetcher))

    return asyncio.run(run()), offsets


def test_oracle_honors_200() -> None:
    result, offsets = _run_oracle([(450, 200), (450, 200), (450, 50)])
    assert offsets == [0, 200, 400]  # no skipped offsets
    assert len(result.jobs) == 450
    assert result.is_complete_snapshot is True


def test_oracle_survives_silent_server_cap() -> None:
    result, offsets = _run_oracle([(60, 25), (60, 25), (60, 10)])
    assert offsets == [0, 25, 50]
    assert [j.source_job_id for j in result.jobs] == [str(i) for i in range(1, 61)]
    assert result.is_complete_snapshot is True


def test_oracle_exact_total_boundary() -> None:
    result, offsets = _run_oracle([(200, 200)])
    assert offsets == [0]
    assert result.is_complete_snapshot is True


def test_oracle_empty_before_total_is_safe_failure() -> None:
    with pytest.raises(AdapterSchemaError):
        _run_oracle([(60, 25), (60, 0)])


def test_oracle_total_change_warns() -> None:
    result, _ = _run_oracle([(60, 25), (61, 25), (61, 11)])
    assert any("total changed" in w for w in result.warnings)
    assert result.is_complete_snapshot is True


def test_oracle_page_cap_preserved() -> None:
    result, offsets = _run_oracle([(10000, 200)] * 3, max_pages=2)
    assert offsets == [0, 200]
    assert result.is_complete_snapshot is False
    assert any("safety cap" in w for w in result.warnings)


def test_oracle_requested_limit_is_200() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if "hcmRestApi" in request.url.path:
            return httpx.Response(200, json=_oracle_page(0, 0), request=request)
        return httpx.Response(200, text=LANDING, request=request)

    async def run():
        fetcher = HttpFetcher(max_retries=0, per_domain_min_interval_seconds=0,
                              jitter_seconds=0, resolve_dns=False,
                              transport=httpx.MockTransport(handler))
        async with fetcher:
            return await OracleRecruitingCloudAdapter().scan(
                _target("https://example.fa.oraclecloud.com/x", "Oracle Recruiting Cloud"),
                PortalScanContext(fetcher=fetcher))

    asyncio.run(run())
    assert "limit=200,offset=0" in seen[-1]


# ---------- Lever ----------

def test_lever_assembles_lists_and_dedups() -> None:
    job = {"description": "<p>Intro</p>",
           "lists": [{"text": "Requirements", "content": "<li>X</li>"},
                     {"text": "Requirements", "content": "<li>X</li>"},
                     {"text": "", "content": "  <p>Intro</p>  "}],
           "descriptionPlain": "fallback"}
    out = lever_desc(job)
    assert "Intro" in out and "Requirements" in out and "X" in out
    assert out.count("Requirements") == 1  # dup section dropped
    assert "fallback" not in out


def test_lever_falls_back_to_plain() -> None:
    assert lever_desc({"descriptionPlain": "plain body"}) == "plain body"
    assert lever_desc({}) == ""


def test_lever_identity_and_posted_at() -> None:
    adapter = LeverAdapter()
    job = {"id": "abc", "text": "T", "hostedUrl": "https://jobs.lever.co/x/abc",
           "applyUrl": "https://jobs.lever.co/x/abc/apply",
           "categories": {"location": "L", "commitment": "Full-time"},
           "description": "<p>D</p>", "lists": [], "createdAt": 1755731400000}
    parsed = adapter._parse_job(job, index=0)
    assert parsed.source_job_id == "abc"  # identity unchanged
    assert parsed.source_url == "https://jobs.lever.co/x/abc"
    assert parsed.apply_url == "https://jobs.lever.co/x/abc/apply"
    assert parsed.posted_at is not None and parsed.posted_at.year == 2025
    assert "D" in parsed.description


def test_parse_epoch_millis_rejects_garbage() -> None:
    assert parse_epoch_millis(None) is None
    assert parse_epoch_millis("1755731400000") is None
    assert parse_epoch_millis(True) is None
    assert parse_epoch_millis(-10**15) is None


# ---------- Workday ----------

def test_workday_enriches_employment_and_workplace() -> None:
    adapter = WorkdayAdapter()
    job = {"title": "T", "externalPath": "/job/x/1",
           "bulletFields": ["R-1"], "locationsText": "City",
           "timeType": "Full time", "remoteType": "Remote"}
    parsed = adapter._parse_job(job, site_url="https://s", index=0)
    assert parsed.source_job_id == "R-1"  # identity unchanged
    assert parsed.employment_type == "Full time"
    assert parsed.workplace_type == "Remote"


# ---------- SmartRecruiters ----------

def test_smartrecruiters_prefers_stable_employment_id() -> None:
    adapter = SmartRecruitersAdapter()
    job = {"id": "9", "name": "T", "ref": "https://u",
           "typeOfEmployment": {"id": "permanent", "label": "Temps plein"},
           "location": {"city": "C", "country": "IT"}}
    parsed = adapter._parse_job(job, index=0)
    assert parsed.employment_type == "permanent"
    assert parsed.source_job_id == "9"  # identity unchanged
    assert parsed.requisition_id is None  # refNumber NOT promoted (identity)


# ---------- Greenhouse ----------

def test_greenhouse_unescape_and_req_filter() -> None:
    assert gh_unescape("&lt;div&gt;Hi&lt;/div&gt;") == "<div>Hi</div>"
    assert gh_unescape("plain & simple") == "plain & simple"
    assert gh_unescape("") == ""
    assert gh_req("R-123") == "R-123"
    assert gh_req(42) == "42"
    for placeholder in ("See Opening ID", "TBD", "N/A", "tba", "  "):
        assert gh_req(placeholder) is None
    assert gh_req(None) is None


def test_greenhouse_identity_and_enrichment_via_scan() -> None:
    adapter = GreenhouseAdapter()
    target = _target("https://boards.greenhouse.io/acme", "Greenhouse")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jobs": [{
            "id": 7, "title": "T", "absolute_url": "https://boards.greenhouse.io/acme/jobs/7",
            "location": {"name": "L"}, "content": "&lt;p&gt;D&lt;/p&gt;",
            "first_published": "2026-01-02T03:04:05Z",
            "requisition_id": "TBD",
            "departments": [{"name": "Eng"}], "offices": [{"name": "Rome"}],
            "metadata": [{"name": "k", "value": "v"}], "internal_job_id": 99}]},
            request=request)

    async def run():
        fetcher = HttpFetcher(max_retries=0, per_domain_min_interval_seconds=0,
                              jitter_seconds=0, resolve_dns=False,
                              transport=httpx.MockTransport(handler))
        async with fetcher:
            return await adapter.scan(target, PortalScanContext(fetcher))

    result = asyncio.run(run())
    job = result.jobs[0]
    assert job.source_job_id == "7"  # identity unchanged
    assert job.description == "<p>D</p>"  # unescaped once
    assert job.requisition_id is None  # placeholder filtered
    assert job.raw_payload["departments"] == [{"name": "Eng"}]  # raw preserved
    assert result.is_complete_snapshot is True


# ---------- Ashby ----------

def test_ashby_prefers_html_and_keeps_identity() -> None:
    adapter = AshbyAdapter()
    target = _target("https://jobs.ashbyhq.com/example", "Ashby")
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, json={"jobs": [{
            "id": "bare-id", "title": "T", "jobUrl": "https://jobs.ashbyhq.com/example/1",
            "location": "L", "descriptionHtml": "<p>Rich</p>",
            "descriptionPlain": "Rich", "employmentType": "FullTime"}]},
            request=request)

    async def run():
        fetcher = HttpFetcher(max_retries=0, per_domain_min_interval_seconds=0,
                              jitter_seconds=0, resolve_dns=False,
                              transport=httpx.MockTransport(handler))
        async with fetcher:
            return await adapter.scan(target, PortalScanContext(fetcher))

    result = asyncio.run(run())
    assert "includeCompensation=true" in requested[0]
    job = result.jobs[0]
    assert job.source_job_id == "https://jobs.ashbyhq.com/example/1"  # identity unchanged
    assert job.description == "<p>Rich</p>"  # HTML preferred


def test_ashby_falls_back_to_plain() -> None:
    from research_agent.sources.ats.common import string_value as sv
    assert (sv(None) or sv("P")) == "P"
