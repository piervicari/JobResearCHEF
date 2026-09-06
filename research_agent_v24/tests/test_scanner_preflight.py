"""Scanner-level preflight wiring tests (offline hardening patch).

Proves the NORMAL scan_portals() path invokes the optional generic
adapter preflight hook after select() and before anything that could
touch the network — fail closed, zero HTTP. Uses httpx.MockTransport
throughout (resolve_dns=False is automatic when a transport is given).
"""
from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_agent.config import ScannerSettings
from research_agent.db.migrations import create_schema
from research_agent.db.models import ImportBatch, Portal
from research_agent.pipeline.scanner import ScanSummary, scan_portals
from research_agent.sources.base import (
    AdapterRegistry,
    AdapterScanResult,
    PortalScanContext,
    PortalTarget,
)

MERCEDES_PORTAL = "https://jobs.mercedes-benz.com"


def _seed_portal(engine: Engine, portal_url: str, ats_family: str = "test") -> int:
    create_schema(engine)
    with Session(engine) as session, session.begin():
        batch = ImportBatch(
            source_kind="test",
            source_filename="fixture.csv",
            source_path="fixture.csv",
            source_sha256="b" * 64,
            source_version="test",
            status="COMPLETED",
        )
        session.add(batch)
        session.flush()
        portal = Portal(
            normalized_jobs_url=portal_url,
            jobs_search_url=portal_url,
            scheme="https",
            host=httpx.URL(portal_url).host,
            ats_families_json=json.dumps([ats_family]),
            ats_confidences_json='["Verified"]',
            metadata_conflict=False,
            cluster_count=1,
            active_in_registry=True,
            import_batch_id=batch.id,
        )
        session.add(portal)
        session.flush()
        return portal.id


def _settings(**overrides) -> ScannerSettings:
    return ScannerSettings(**overrides)


def test_blocked_preflight_reaches_no_network(sqlite_engine: Engine, tmp_path: Path):
    """§7: bound Mercedes portal, active unsupported safety requirement
    (long pauses) → FAILED before a single request."""
    from research_agent.sources.declarative import load_declarative_adapter

    calls: list[httpx.Request] = []

    def exploding_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, content=b"{}", request=request)

    portal_id = _seed_portal(sqlite_engine, MERCEDES_PORTAL)
    summary = asyncio.run(
        scan_portals(
            sqlite_engine,
            AdapterRegistry([load_declarative_adapter()]),
            _settings(),
            portal_ids={portal_id},
            transport=httpx.MockTransport(exploding_handler),
            cache_directory=tmp_path / "cache",
        )
    )
    assert isinstance(summary, ScanSummary)
    assert summary.success_count == 0
    assert summary.failure_count == 1
    (result,) = summary.portal_results
    assert result.status == "FAILED"
    assert result.error_type == "UnsafeToRunError"
    assert "UNSUPPORTED_SAFETY_REQUIREMENT" in (result.error_message or "")
    assert "long_pause" in (result.error_message or "")
    assert result.jobs == ()
    assert result.fetch_attempts == ()
    assert result.complete_snapshot is False
    assert result.final_http_status is None
    assert calls == []


def _synthetic_spec(base_spec: dict) -> dict:
    spec = copy.deepcopy(base_spec)
    spec["company"] = {"id": "synthetic", "name": "Synthetic Co"}
    spec["safety"] = {
        "sequential_only": True,
        "min_seconds_between_requests": 0.5,
        "long_pause_every_n_requests": 0,
        "long_pause_seconds": 0,
        "max_requests_per_run": 600,
        "abort_on_http_403": True,
        "abort_on_http_429": True,
        "max_retries_on_5xx": 1,
        "max_consecutive_errors": 0,
    }
    return spec


def _synthetic_adapter(tmp_path: Path, portal_url: str):
    from research_agent.sources.declarative.adapter import (
        DeclarativeSourceAdapter,
        DeclarativeSourceBinding,
    )

    # Reuse the shipped NVIDIA wire shape; only company + safety differ.
    decl_dir = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "research_agent"
        / "sources"
        / "declarative"
    )
    base = json.loads((decl_dir / "specs" / "nvidia.json").read_text(encoding="utf-8"))
    (tmp_path / "spec.json").write_text(json.dumps(_synthetic_spec(base)), encoding="utf-8")
    return DeclarativeSourceAdapter(
        [DeclarativeSourceBinding(portal_url, "spec.json")],
        base_dir=tmp_path,
    )


def _eightfold_pages(total: int):
    def handler(request: httpx.Request) -> httpx.Response:
        query = dict(httpx.QueryParams(request.url.query))
        start = int(query.get("start", 0))
        items = [
            {
                "id": f"S-{i:05d}",
                "displayJobId": f"D-{i:05d}",
                "atsJobId": f"A-{i:05d}",
                "name": f"Role {i}",
                "department": "Engineering",
                "postedTs": 1756684800,
                "locations": ["Nowhere"],
                "publicUrl": f"https://syn.example.test/j/S-{i:05d}",
            }
            for i in range(start, min(start + 10, total))
        ]
        return httpx.Response(
            200, json={"data": {"positions": items, "count": total}}, request=request
        )

    return handler


def test_too_permissive_settings_blocked_with_zero_calls(
    sqlite_engine: Engine, tmp_path: Path
):
    """§8: spec allows max 1 retry, settings use 2 → TOO_PERMISSIVE,
    UnsafeToRunError, zero HTTP calls, zero fetch attempts."""
    portal_url = "https://syn2.example.test/jobs"
    portal_id = _seed_portal(sqlite_engine, portal_url)
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return _eightfold_pages(12)(request)

    summary = asyncio.run(
        scan_portals(
            sqlite_engine,
            AdapterRegistry([_synthetic_adapter(tmp_path, portal_url)]),
            _settings(max_retries=2),
            portal_ids={portal_id},
            transport=httpx.MockTransport(handler),
            cache_directory=tmp_path / "cache",
        )
    )
    (result,) = summary.portal_results
    assert result.status == "FAILED"
    assert result.error_type == "UnsafeToRunError"
    assert "SCANNER_SETTINGS_TOO_PERMISSIVE" in (result.error_message or "")
    assert result.fetch_attempts == ()
    assert calls == []


def test_safe_preflight_runs_normal_scan(sqlite_engine: Engine, tmp_path: Path):
    """§9: compatible settings → preflight passes → normal scan through
    the mock transport (guards against a patch that blocks everything)."""
    portal_url = "https://syn3.example.test/jobs"
    portal_id = _seed_portal(sqlite_engine, portal_url)
    calls: list[httpx.Request] = []
    inner = _eightfold_pages(12)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return inner(request)

    summary = asyncio.run(
        scan_portals(
            sqlite_engine,
            AdapterRegistry([_synthetic_adapter(tmp_path, portal_url)]),
            _settings(
                per_domain_min_interval_seconds=0.5,
                max_retries=1,
                max_requests_per_run=600,
            ),
            portal_ids={portal_id},
            transport=httpx.MockTransport(handler),
            cache_directory=tmp_path / "cache",
        )
    )
    assert summary.success_count == 1
    (result,) = summary.portal_results
    assert result.status == "SUCCESS"
    assert result.adapter == "declarative"
    assert len(result.jobs) == 12
    assert result.complete_snapshot is True
    assert len(calls) == 2
    assert {job.source for job in result.jobs} == {"declarative:synthetic"}


def test_legacy_adapter_without_preflight_unaffected(
    sqlite_engine: Engine, tmp_path: Path
):
    """§10: a legacy adapter with no preflight hook is selected and scans
    normally — no AttributeError, no declarative safety semantics."""
    from research_agent.sources.ats.smartrecruiters import SmartRecruitersAdapter
    from research_agent.sources.ats.registry import structured_adapter_registry

    assert not hasattr(SmartRecruitersAdapter(), "preflight")
    portal_url = "https://careers.smartrecruiters.com/exampleco"
    portal_id = _seed_portal(sqlite_engine, portal_url, ats_family="SmartRecruiters")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "content": [
                    {
                        "id": "sr-1",
                        "name": "Security Analyst",
                        "company": {"name": "Example Co"},
                        "location": {"city": "Milan", "region": "", "country": "Italy"},
                        "ref": "https://jobs.smartrecruiters.com/ExampleCo/sr-1",
                    }
                ],
                "totalFound": 1,
            },
            request=request,
        )

    summary = asyncio.run(
        scan_portals(
            sqlite_engine,
            structured_adapter_registry(),
            _settings(),
            portal_ids={portal_id},
            transport=httpx.MockTransport(handler),
            cache_directory=tmp_path / "cache",
        )
    )
    assert summary.success_count == 1
    (result,) = summary.portal_results
    assert result.status == "SUCCESS"
    assert result.adapter == "smartrecruiters"
    assert len(result.jobs) == 1


class _RecordingAdapter:
    """Generic hook-shape probe: no SourceSpec anywhere near it."""

    name = "fake-recording"

    def __init__(self, events: list[str], *, fail_preflight: bool = False) -> None:
        self._events = events
        self._fail = fail_preflight

    def supports(self, target: PortalTarget) -> bool:
        return True

    def preflight(self, target: PortalTarget, settings: object) -> None:
        self._events.append("preflight")
        if self._fail:
            raise RuntimeError("synthetic safety veto")

    async def scan(
        self, target: PortalTarget, context: PortalScanContext
    ) -> AdapterScanResult:
        self._events.append("scan")
        return AdapterScanResult(jobs=(), warnings=(), is_complete_snapshot=True)


def _seeded_engine_with_portal(sqlite_engine: Engine) -> int:
    return _seed_portal(sqlite_engine, "https://fake.example.test/jobs")


def test_preflight_runs_before_scan_on_success(
    sqlite_engine: Engine, tmp_path: Path
):
    """§15: hook order is [preflight, scan] through the normal path."""
    events: list[str] = []
    portal_id = _seeded_engine_with_portal(sqlite_engine)
    summary = asyncio.run(
        scan_portals(
            sqlite_engine,
            AdapterRegistry([_RecordingAdapter(events)]),
            _settings(),
            portal_ids={portal_id},
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, content=b"{}", request=request)
            ),
            cache_directory=tmp_path / "cache",
        )
    )
    assert summary.success_count == 1
    assert events == ["preflight", "scan"]


def test_failing_preflight_prevents_scan(sqlite_engine: Engine, tmp_path: Path):
    """§15: failing hook → ['preflight'] only, FAILED, zero network."""
    events: list[str] = []
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, content=b"{}", request=request)

    portal_id = _seeded_engine_with_portal(sqlite_engine)
    summary = asyncio.run(
        scan_portals(
            sqlite_engine,
            AdapterRegistry([_RecordingAdapter(events, fail_preflight=True)]),
            _settings(),
            portal_ids={portal_id},
            transport=httpx.MockTransport(handler),
            cache_directory=tmp_path / "cache",
        )
    )
    assert events == ["preflight"]
    assert summary.failure_count == 1
    (result,) = summary.portal_results
    assert result.status == "FAILED"
    assert result.error_type == "RuntimeError"
    assert result.fetch_attempts == ()
    assert calls == []


def test_scanner_knows_no_source_specifics():
    """§16: the generic hook path names no source, platform or vendor.
    (One pre-existing comment line mentions Greenhouse/Ashby as an
    example; it predates the hook and is excluded so this test guards
    new code, not history.)"""
    import re

    text = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "research_agent"
        / "pipeline"
        / "scanner.py"
    ).read_text(encoding="utf-8")
    text = "\n".join(
        line
        for line in text.splitlines()
        if "for example Greenhouse/Ashby" not in line
    ).lower()
    for token in (
        "declarative",
        "source_spec",
        "sourcespec",
        "mercedes",
        "nvidia",
        "microsoft",
        "eightfold",
        "beesite",
        "greenhouse",
    ):
        assert re.search(r"\b" + re.escape(token) + r"\b", text) is None, (
            f"scanner.py mentions {token!r}"
        )
