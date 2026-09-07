"""Teamtailor + Workable adapter tests (offline; fixtures from Wave 1.1 live bodies).

Provenance: tests/fixtures/teamtailor_jobs.json (first 3 items of the
verified polestar jobs.json) and workable_jobs.json (3 shortcodes of the
verified starling-bank ?details=true widget). Shapes are real wire data,
trimmed for size. Zero live HTTP (httpx.MockTransport throughout).
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from research_agent.pipeline.http import (
    HostCircuitOpenError,
    HttpFetcher,
    FetchRequest,
)
from research_agent.sources.ats.common import AdapterHttpError, AdapterSchemaError
from research_agent.sources.ats.registry import (
    default_adapter_registry,
    structured_adapter_registry,
)
from research_agent.sources.ats.teamtailor import TeamtailorAdapter
from research_agent.sources.ats.workable import WorkableAdapter
from research_agent.sources.base import PortalScanContext, PortalTarget

FIXTURES = Path(__file__).resolve().parent / "fixtures"

TT_PORTAL = "https://polestar.teamtailor.com"
WK_PORTAL = "https://apply.workable.com/starling-bank"


def _target(url: str, families: tuple[str, ...], host: str) -> PortalTarget:
    return PortalTarget(
        portal_id=1,
        jobs_search_url=url,
        normalized_jobs_url=url,
        host=host,
        ats_families=families,
        ats_confidences=(),
    )


def _tt_target(url: str = TT_PORTAL) -> PortalTarget:
    return _target(url, ("Teamtailor",), "polestar.teamtailor.com")


def _wk_target(url: str = WK_PORTAL) -> PortalTarget:
    return _target(url, ("Workable",), "apply.workable.com")


def _run(adapter, target, handler, **context_kwargs):
    requested: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        requested.append(request)
        return handler(request)

    async def run():
        fetcher = HttpFetcher(
            max_retries=0,
            per_domain_min_interval_seconds=0,
            jitter_seconds=0,
            resolve_dns=False,
            transport=httpx.MockTransport(recording),
        )
        async with fetcher:
            context = PortalScanContext(
                fetcher=fetcher, max_pages_per_portal=30, max_jobs_per_portal=500,
                **context_kwargs,
            )
            return await adapter.scan(target, context)

    return asyncio.run(run()), requested


def _tt_handler(items) -> object:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": items}, request=request)

    return handler


def _wk_handler(payload: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload, request=request)

    return handler


def _tt_fixture() -> list:
    return json.loads((FIXTURES / "teamtailor_jobs.json").read_text(encoding="utf-8"))["items"]


def _wk_fixture() -> dict:
    return json.loads((FIXTURES / "workable_jobs.json").read_text(encoding="utf-8"))


# ---------- fixture parse + normalization ----------

def test_teamtailor_parses_real_fixture() -> None:
    result, requested = _run(TeamtailorAdapter(), _tt_target(), _tt_handler(_tt_fixture()))
    assert len(requested) == 1  # single-request catalog, no N+1
    assert requested[0].url.path == "/jobs.json"
    assert len(result.jobs) == 3
    first = result.jobs[0]
    assert first.source == "teamtailor"
    assert first.source_job_id == "8319785"  # numeric ID from public URL
    assert first.title == "Salesforce Solution Architect"
    assert first.location == "Göteborg, Nordics & UK, SE"
    assert "salesforce" in first.description.lower()
    assert first.apply_url.startswith("https://polestar.teamtailor.com/jobs/8319785-")
    assert result.is_complete_snapshot is True


def test_workable_parses_real_fixture_with_dedup() -> None:
    result, requested = _run(WorkableAdapter(), _wk_target(), _wk_handler(_wk_fixture()))
    assert len(requested) == 1  # single catalog request, no detail N+1
    assert "details=true" in str(requested[0].url)
    assert len(result.jobs) == 3  # 4 rows, 3 unique shortcodes
    android = [j for j in result.jobs if j.source_job_id == "0DA49B0B28"][0]
    assert android.title == "Android Engineer"
    assert "Manchester" in android.location and "Cardiff" in android.location
    assert android.company == "Starling"
    assert android.description.strip() != ""
    assert result.is_complete_snapshot is True


# ---------- empty / malformed ----------

def test_teamtailor_empty_items_is_valid_empty_snapshot() -> None:
    result, _ = _run(TeamtailorAdapter(), _tt_target(), _tt_handler([]))
    assert result.jobs == ()
    assert result.is_complete_snapshot is True
    assert any("zero active jobs" in w for w in result.warnings)


def test_teamtailor_404_is_not_authoritative_empty() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b"nope", request=request)

    with pytest.raises(AdapterHttpError):
        _run(TeamtailorAdapter(), _tt_target(), handler)


def test_teamtailor_malformed_shape_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"nope": []}, request=request)

    with pytest.raises(AdapterSchemaError):
        _run(TeamtailorAdapter(), _tt_target(), handler)


def test_workable_empty_jobs_is_not_authoritative() -> None:
    """200 + jobs:[] is ambiguous on Workable (unknown accounts answer the
    same): complete=false with an explicit warning, never empty snapshot."""
    result, _ = _run(
        WorkableAdapter(), _wk_target(), _wk_handler({"name": "Nobody", "jobs": []})
    )
    assert result.jobs == ()
    assert result.is_complete_snapshot is False
    assert any("ambiguous" in w for w in result.warnings)


def test_workable_missing_id_or_title_raises() -> None:
    bad = {"name": "X", "jobs": [{"title": "NoId", "url": "https://x.example.test/1"}]}
    with pytest.raises(AdapterSchemaError):
        _run(WorkableAdapter(), _wk_target(), _wk_handler(bad))


# ---------- 403 / 429 ----------

def test_teamtailor_403_uses_standard_failure_path() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, content=b"denied", request=request)

    with pytest.raises(AdapterHttpError):
        _run(TeamtailorAdapter(), _tt_target(), handler)


def test_workable_429_opens_circuit_without_retry() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(429, content=b"slow", request=request)

    with pytest.raises(HostCircuitOpenError):
        _run(WorkableAdapter(), _wk_target(), handler)
    assert len(calls) == 1


# ---------- registry selection ----------

def test_registry_selects_new_adapters_deterministically() -> None:
    for registry in (default_adapter_registry(), structured_adapter_registry()):
        selected_tt = registry.select(_tt_target())
        assert isinstance(selected_tt, TeamtailorAdapter)
        selected_wk = registry.select(_wk_target())
        assert isinstance(selected_wk, WorkableAdapter)


def test_teamtailor_custom_domain_needs_family_label() -> None:
    other = _target("https://jobs.example.test/", (), "jobs.example.test")
    assert TeamtailorAdapter().supports(other) is False
    labeled = _target("https://jobs.example.test/", ("Teamtailor",), "jobs.example.test")
    assert TeamtailorAdapter().supports(labeled) is True


def test_workable_requires_host_and_family() -> None:
    assert WorkableAdapter().supports(_wk_target()) is True
    no_family = _target(WK_PORTAL, (), "apply.workable.com")
    assert WorkableAdapter().supports(no_family) is False


# ---------- no N+1 anti-cheat ----------

def test_catalog_scans_issue_exactly_one_fetch() -> None:
    _, tt_requested = _run(TeamtailorAdapter(), _tt_target(), _tt_handler(_tt_fixture()))
    _, wk_requested = _run(WorkableAdapter(), _wk_target(), _wk_handler(_wk_fixture()))
    assert len(tt_requested) == 1
    assert len(wk_requested) == 1


# ---------- HttpFetcher only (no direct httpx/network in adapters) ----------

def test_adapters_use_fetcher_only() -> None:
    import ast as _ast

    for module in ("teamtailor", "workable"):
        tree = _ast.parse(
            (Path(__file__).resolve().parent.parent
             / "src" / "research_agent" / "sources" / "ats" / f"{module}.py"
             ).read_text(encoding="utf-8")
        )
        imported: set[str] = set()
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, _ast.ImportFrom) and node.module:
                imported.add(node.module)
        assert not ({"httpx", "requests", "aiohttp"} & {m.split(".")[0] for m in imported})
        assert "context.fetch" in (
            Path(__file__).resolve().parent.parent
            / "src" / "research_agent" / "sources" / "ats" / f"{module}.py"
        ).read_text(encoding="utf-8")


def test_fetch_request_contract_untouched() -> None:
    req = FetchRequest("https://polestar.teamtailor.com/jobs.json")
    assert req.wire_policy is None and req.max_retries is None
