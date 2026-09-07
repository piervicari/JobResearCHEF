
"""Phase 3 structured-detail tests (appendix to test_detail_enrichment.py).

Offline only: synthetic ATS JSON per Wave-2 documented shapes, sqlite
temp DB, and a fake HttpFetcher (monkeypatched) for the enrich loop.
Covers B23/B24/B25/B20: per-provider render+parse, selection gating,
idempotent AI requeue, and zero-detail catalog scans.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from research_agent.config import ScannerSettings
from research_agent.db.migrations import create_schema
from research_agent.db.models import ScanRun, SourceJob
from research_agent.pipeline.detail_enrichment import (
    _join_sections,
    _load_declarative_spec,
    _parse_declarative_detail,
    _parse_oracle_detail,
    _parse_smartrecruiters_detail,
    _parse_workday_detail,
    _render_declarative_detail,
    _render_oracle_detail,
    _render_smartrecruiters_detail,
    _render_workday_detail,
    _StructuredRow,
    enrich_official_html_details,
    select_detail_candidates,
)
from research_agent.pipeline.http import (
    HostCircuitOpenError,
    HttpFetcher,
)
from research_agent.sources.ats.oracle import OracleRecruitingCloudAdapter
from research_agent.sources.ats.smartrecruiters import SmartRecruitersAdapter
from research_agent.sources.ats.workday import WorkdayAdapter
from research_agent.sources.base import PortalScanContext, PortalTarget
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from datetime import UTC, datetime

from test_detail_enrichment import _seed_workday_portal


def _row(adapter: str, **kw) -> _StructuredRow:
    base = {
        "adapter": adapter, "source_name": adapter, "source_url": "",
        "portal_host": "example.test", "portal_jobs_url": "https://example.test/",
        "native_id": "", "ats_id": "", "raw_payload": {},
    }
    base.update(kw)
    return _StructuredRow(**base)


# ---------- render + parse unit ----------

def test_workday_structured_render_and_parse() -> None:
    row = _row(
        "workday",
        source_url="https://acme.wd3.myworkdayjobs.com/AcmeSite/job/x/1",
        portal_host="acme.wd3.myworkdayjobs.com",
        raw_payload={"externalPath": "/job/x/1"},
    )
    request = _render_workday_detail(row)
    assert request is not None
    assert request.url == (
        "https://acme.wd3.myworkdayjobs.com/wday/cxs/acme/AcmeSite/job/x/1"
    )
    parsed = _parse_workday_detail(
        {"jobPostingInfo": {
            "jobDescription": "<p>Build things.</p>",
            "location": "Berlin", "additionalLocations": ["Munich", "Berlin"],
            "timeType": "Full time", "remoteType": "Hybrid"}},
        request.url,
    )
    assert parsed.parser == "workday_cxs_detail"
    assert "Build things." in parsed.description
    assert parsed.location == "Berlin | Munich"
    assert parsed.employment_type == "Full time"
    assert parsed.workplace_type == "Hybrid"


def test_smartrecruiters_structured_render_and_parse() -> None:
    row = _row(
        "smartrecruiters",
        portal_jobs_url="https://careers.smartrecruiters.com/Acme",
        ats_id="9",
    )
    request = _render_smartrecruiters_detail(row)
    assert request is not None
    assert request.url == (
        "https://api.smartrecruiters.com/v1/companies/Acme/postings/9"
    )
    parsed = _parse_smartrecruiters_detail(
        {"jobAd": {"sections": {
            "jobDescription": {"text": "<p>Build APIs.</p>"},
            "qualifications": {"text": "<p>Write tests.</p>"},
            "jobDescription_dup": {"text": "<p>Build APIs.</p>"},
        }},
         "location": {"city": "Milan", "country": "IT"}},
        request.url,
    )
    assert parsed.parser == "smartrecruiters_posting_detail"
    assert "Build APIs." in parsed.description
    assert "Write tests." in parsed.description
    assert parsed.description.count("Build APIs.") == 1  # no dup sections
    assert parsed.location == "Milan, IT"


def test_oracle_structured_render_and_parse() -> None:
    row = _row(
        "oracle",
        source_url="https://x.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/42",
        portal_host="x.fa.oraclecloud.com",
        ats_id="42",
    )
    request = _render_oracle_detail(row)
    assert request is not None
    assert "recruitingCEJobRequisitionDetails" in request.url
    assert "finder=ById;Id=42" in request.url
    parsed = _parse_oracle_detail(
        {"items": [{"ExternalDescriptionStr": "<p>Desc.</p>",
                    "ExternalQualificationsStr": "<p>Qual.</p>",
                    "PrimaryLocation": "Prague",
                    "WorkerType": "Full-Time"}]},
        request.url,
    )
    assert parsed.parser == "oracle_byid_detail"
    assert "Desc." in parsed.description and "Qual." in parsed.description
    assert parsed.location == "Prague"
    assert parsed.employment_type == "Full-Time"


def test_structured_declarative_render_and_parse() -> None:
    row = _row(
        "declarative",
        source_name="declarative:nvidia",
        native_id="563087414352251",
        portal_host="jobs.nvidia.com",
        portal_jobs_url="https://jobs.nvidia.com/careers",
    )
    request = _render_declarative_detail(row)
    assert request is not None
    assert "position_details" in request.url
    assert "position_id=563087414352251" in request.url
    spec = _load_declarative_spec("nvidia")
    assert spec is not None
    parsed = _parse_declarative_detail(
        {"data": {"jobDescription": "<p>GPU work.</p>"}}, request.url, spec
    )
    assert parsed.parser == "declarative_spec_detail"
    assert "GPU work." in parsed.description


def test_microsoft_cross_host_sanctioned_and_faithful() -> None:
    """careers.microsoft.com portal → microsoft.eightfold.ai detail host is
    allowed ONLY because the bound Microsoft SourceSpec declares it; the
    full rendered request (method/headers/query) reaches the fetcher."""
    row = _row(
        "declarative",
        source_name="declarative:microsoft",
        native_id="910117342851777",
        portal_host="careers.microsoft.com",
        portal_jobs_url="https://careers.microsoft.com",
    )
    request = _render_declarative_detail(row)
    assert request is not None
    assert request.method == "GET"  # method preserved, not assumed
    assert "microsoft.eightfold.ai" in request.url  # sanctioned cross-host
    assert "careers.microsoft.com" not in request.url
    for param in ("position_id=910117342851777", "domain=microsoft.com", "hl="):
        assert request.url.count(param) == 1  # each query exactly once
    assert request.headers.get("Accept-Language")  # spec header fidelity
    assert request.headers.get("Accept") == "application/json"
    spec = _load_declarative_spec("microsoft")
    assert spec is not None
    parsed = _parse_declarative_detail(
        {"data": {"jobDescription": "<p>MS work.</p>"}}, request.url, spec
    )
    assert "MS work." in parsed.description  # data.jobDescription resolves


def test_microsoft_enrich_flow_persists_and_requeues(
    sqlite_engine: Engine, monkeypatch,
) -> None:
    create_schema(sqlite_engine)
    _seed_portal(sqlite_engine, 781, "careers.microsoft.com",
                 "https://careers.microsoft.com")
    job_id = _add_structured_job(
        sqlite_engine, 781, adapter="declarative",
        source="declarative:microsoft",
        source_url="https://careers.microsoft.com/us/en/job/123",
        native_id="910117342851777", ai_status="CYBER")
    seen: list = []

    def handler(request):
        seen.append(request)
        return _FakeResponse(
            {"data": {"jobDescription": "<p>MS work.</p>"}},
            url="https://microsoft.eightfold.ai/api/pcsx/position_details")

    _patch_fetcher(monkeypatch, handler)
    summary = asyncio.run(enrich_official_html_details(
        sqlite_engine, ScannerSettings(), limit=5, inter_job_wait_seconds=0))
    assert summary.updated_jobs == 1 and summary.failed_jobs == 0
    assert seen and seen[0].method == "GET"
    assert seen[0].headers.get("Accept-Language")
    assert "position_id=910117342851777" in seen[0].url
    with Session(sqlite_engine) as session:
        row = session.get(SourceJob, job_id)
        assert "MS work." in row.detail_description
        assert row.ai_status == "PENDING_AI"


def test_unsanctioned_cross_host_rejected_before_http(
    sqlite_engine: Engine, monkeypatch,
) -> None:
    """A declarative row whose portal is NOT bound to its source company
    yields no candidate: 0 wire, even though the spec itself is genuine."""
    create_schema(sqlite_engine)
    _seed_portal(sqlite_engine, 791, "evil.example.test",
                 "https://evil.example.test/jobs")
    _add_structured_job(
        sqlite_engine, 791, adapter="declarative",
        source="declarative:microsoft",  # genuine spec, wrong portal
        source_url="https://evil.example.test/jobs/1",
        native_id="910117342851777", ai_status="CYBER")

    def handler(request):
        raise AssertionError("must never fetch")

    fakes = _patch_fetcher(monkeypatch, handler)
    summary = asyncio.run(enrich_official_html_details(
        sqlite_engine, ScannerSettings(), limit=5, inter_job_wait_seconds=0))
    assert summary.selected_jobs == 0 and summary.requests == 0
    assert fakes == []  # early return: no HttpFetcher even constructed


def test_structured_render_none_when_unrenderable() -> None:
    assert _render_workday_detail(_row("workday", source_url="https://h.test/no-job-here")) is None
    assert _render_smartrecruiters_detail(_row("smartrecruiters")) is None
    assert _render_oracle_detail(_row("oracle", source_url="https://h.test/x")) is None
    unknown = _row("declarative", source_name="declarative:nope",
                   native_id="1", portal_host="h.test")
    assert _render_declarative_detail(unknown) is None
    assert _load_declarative_spec("../evil") is None


def test_join_sections_dedups_and_orders() -> None:
    out = _join_sections("<p>A</p>", "", "<p>B</p>", "<p>A</p>")
    assert out == "A\n\nB"


# ---------- selection gating ----------

def _add_structured_job(
    engine: Engine, portal_id: int, *, adapter: str, source: str,
    source_url: str, native_id: str = "", ats_id: str = "",
    raw_payload: str = "{}", ai_status: str = "NEEDS_MORE_DETAIL",
    raw_description: str = "", detail_description: str = "",
) -> int:
    from research_agent.db.models import SourceJob as SJ
    with Session(engine) as session, session.begin():
        run = ScanRun(
            source="test_fixture", status="COMPLETED",
            started_at=datetime.now(UTC), finished_at=datetime.now(UTC),
            portal_count=1, success_count=1, failure_count=0,
            jobs_discovered=1, pipeline_status="NOT_PROCESSED",
        )
        session.add(run)
        session.flush()
        row = SJ(
            scan_run_id=run.id, portal_id=portal_id, canonical_job_id=None,
            source=source, source_job_id=native_id or source_url.rsplit("/", 1)[-1],
            native_source_job_id=native_id, source_url=source_url,
            apply_url=source_url, canonical_apply_url=source_url,
            raw_title="T", raw_company="C", resolved_corporate_cluster_id="CG",
            resolved_company_name="C", raw_description=raw_description,
            detail_description=detail_description,
            ats_job_id=ats_id or None,
            fetched_at=datetime.now(UTC), adapter=adapter,
            parser_version="0.1.0", payload_sha256="0" * 64,
            raw_payload_json=raw_payload,
            first_seen_at=datetime.now(UTC), last_seen_at=datetime.now(UTC),
            is_active=True, missing_successful_scans=0, ai_status=ai_status,
        )
        session.add(row)
        session.flush()
        return row.id


def _seed_portal(engine, portal_id: int, host: str, jobs_url: str) -> None:
    _seed_workday_portal(engine, portal_id=portal_id, cluster_id=f"CG-{portal_id}",
                         host=host, jobs_search_url=jobs_url,
                         sha_marker=f"p{portal_id}")


def test_structured_candidates_selected_with_exact_urls(
    sqlite_engine: Engine,
) -> None:
    create_schema(sqlite_engine)
    _seed_portal(sqlite_engine, 701,
                 "acme.wd3.myworkdayjobs.com",
                 "https://acme.wd3.myworkdayjobs.com/AcmeSite")
    _seed_portal(sqlite_engine, 702,
                 "careers.smartrecruiters.com",
                 "https://careers.smartrecruiters.com/Acme")
    _seed_portal(sqlite_engine, 703,
                 "x.fa.oraclecloud.com",
                 "https://x.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1")
    _add_structured_job(
        sqlite_engine, 701, adapter="workday", source="workday",
        source_url="https://acme.wd3.myworkdayjobs.com/AcmeSite/job/x/1",
        native_id="R-1", raw_payload='{"externalPath": "/job/x/1"}')
    _add_structured_job(
        sqlite_engine, 702, adapter="smartrecruiters", source="smartrecruiters",
        source_url="https://jobs.smartrecruiters.com/Acme/9",
        native_id="9", ats_id="9")
    _add_structured_job(
        sqlite_engine, 703, adapter="oracle", source="oracle",
        source_url="https://x.fa.oraclecloud.com/whatever/job/42",
        native_id="42", ats_id="42")
    candidates = select_detail_candidates(sqlite_engine, limit=5)
    by_adapter = {c.adapter: c for c in candidates}
    assert set(by_adapter) == {"workday", "smartrecruiters", "oracle"}
    assert by_adapter["workday"].request_url.endswith("/wday/cxs/acme/AcmeSite/job/x/1")
    assert by_adapter["smartrecruiters"].request_url == (
        "https://api.smartrecruiters.com/v1/companies/Acme/postings/9")
    assert "finder=ById;Id=42" in by_adapter["oracle"].request_url
    assert all(c.structured for c in candidates)


def test_non_cyber_and_inline_complete_never_selected(
    sqlite_engine: Engine,
) -> None:
    create_schema(sqlite_engine)
    _seed_portal(sqlite_engine, 711,
                 "careers.smartrecruiters.com",
                 "https://careers.smartrecruiters.com/Acme")
    _seed_portal(sqlite_engine, 712,
                 "apply.workable.com", "https://apply.workable.com/starling-bank")
    _add_structured_job(
        sqlite_engine, 711, adapter="smartrecruiters", source="smartrecruiters",
        source_url="https://jobs.smartrecruiters.com/Acme/9",
        native_id="9", ats_id="9", ai_status="NON_CYBER")
    _add_structured_job(
        sqlite_engine, 712, adapter="workable", source="workable",
        source_url="https://apply.workable.com/starling-bank/j/1",
        native_id="1", ai_status="CYBER")
    _add_structured_job(
        sqlite_engine, 711, adapter="smartrecruiters", source="smartrecruiters",
        source_url="https://jobs.smartrecruiters.com/Acme/10",
        native_id="10", ats_id="10", ai_status="CYBER",
        detail_description="x" * 600)  # already complete
    assert select_detail_candidates(sqlite_engine, limit=5) == []


def test_unrenderable_structured_row_skipped(
    sqlite_engine: Engine,
) -> None:
    create_schema(sqlite_engine)
    _seed_portal(sqlite_engine, 721,
                 "acme.wd3.myworkdayjobs.com",
                 "https://acme.wd3.myworkdayjobs.com/AcmeSite")
    _add_structured_job(
        sqlite_engine, 721, adapter="workday", source="workday",
        source_url="https://acme.wd3.myworkdayjobs.com/AcmeSite",  # no /job/ path
        native_id="R-1")
    assert select_detail_candidates(sqlite_engine, limit=5) == []


# ---------- actual-host cap (Phase 3 final consistency) ----------

def test_shared_actual_detail_host_cap_across_portals(
    sqlite_engine: Engine,
) -> None:
    """Two DIFFERENT portal hosts whose sanctioned detail requests land on
    one shared actual host (api.smartrecruiters.com): max_jobs_per_host=1
    yields exactly 1 candidate. The cap follows the HTTP host, not portals."""
    create_schema(sqlite_engine)
    _seed_portal(sqlite_engine, 801,
                 "careers-a.example.test",
                 "https://careers-a.example.test/AcmeA")
    _seed_portal(sqlite_engine, 802,
                 "careers-b.example.test",
                 "https://careers-b.example.test/AcmeB")
    _add_structured_job(
        sqlite_engine, 801, adapter="smartrecruiters", source="smartrecruiters",
        source_url="https://jobs.example.test/AcmeA/1",
        native_id="1", ats_id="1", ai_status="CYBER")
    _add_structured_job(
        sqlite_engine, 802, adapter="smartrecruiters", source="smartrecruiters",
        source_url="https://jobs.example.test/AcmeB/2",
        native_id="2", ats_id="2", ai_status="CYBER")
    candidates = select_detail_candidates(
        sqlite_engine, limit=5, max_jobs_per_host=1)
    assert len(candidates) == 1
    assert candidates[0].host == "api.smartrecruiters.com"


def test_same_host_cap_regression(sqlite_engine: Engine) -> None:
    """Portal host == detail host (workday): 3 eligible jobs with
    max_jobs_per_host=2 yield exactly 2 candidates. No behavior change."""
    create_schema(sqlite_engine)
    _seed_portal(sqlite_engine, 811,
                 "acme.wd3.myworkdayjobs.com",
                 "https://acme.wd3.myworkdayjobs.com/AcmeSite")
    for n in ("1", "2", "3"):
        _add_structured_job(
            sqlite_engine, 811, adapter="workday", source="workday",
            source_url=f"https://acme.wd3.myworkdayjobs.com/AcmeSite/job/x/{n}",
            native_id=f"R-{n}",
            raw_payload='{"externalPath": "/job/x/%s"}' % n,
            ai_status="CYBER")
    candidates = select_detail_candidates(
        sqlite_engine, limit=5, max_jobs_per_host=2)
    assert len(candidates) == 2
    assert {c.host for c in candidates} == {"acme.wd3.myworkdayjobs.com"}


def test_microsoft_cap_keyed_on_actual_detail_host(
    sqlite_engine: Engine,
) -> None:
    """Microsoft portal careers.microsoft.com renders detail to
    microsoft.eightfold.ai: cap accounting AND candidate host use the
    actual detail host, while portal identity stays unchanged."""
    create_schema(sqlite_engine)
    _seed_portal(sqlite_engine, 821, "careers.microsoft.com",
                 "https://careers.microsoft.com")
    _add_structured_job(
        sqlite_engine, 821, adapter="declarative",
        source="declarative:microsoft",
        source_url="https://careers.microsoft.com/us/en/job/123",
        native_id="910117342851777", ai_status="CYBER")
    candidates = select_detail_candidates(
        sqlite_engine, limit=5, max_jobs_per_host=2)
    assert len(candidates) == 1
    assert candidates[0].host == "microsoft.eightfold.ai"
    assert "microsoft.eightfold.ai" in candidates[0].request_url
    assert candidates[0].portal_id == 821


# ---------- enrich flow via fake fetcher (no network) ----------

class _FakeResponse:
    def __init__(self, payload=None, status=200, url="https://fake.test/d"):
        self.status_code = status
        self._payload = payload
        self.text = ""
        self.final_url = url

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _FakeFetcher:
    def __init__(self, handler, **kwargs):
        self.handler = handler
        self.requests: list = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def fetch(self, request):
        self.requests.append(request.url)
        return self.handler(request)


def _patch_fetcher(monkeypatch, handler):
    fakes: list = []

    def factory(**kwargs):
        fake = _FakeFetcher(handler, **kwargs)
        fakes.append(fake)
        return fake

    monkeypatch.setattr(
        "research_agent.pipeline.detail_enrichment.HttpFetcher", factory)
    return fakes


SR_SECTIONS = {"jobAd": {"sections": {
    "jobDescription": {"text": "<p>Build APIs.</p>"},
    "qualifications": {"text": "<p>Write tests.</p>"}}}}


def test_structured_hydration_updates_and_requeues(
    sqlite_engine: Engine, monkeypatch,
) -> None:
    create_schema(sqlite_engine)
    _seed_portal(sqlite_engine, 731,
                 "careers.smartrecruiters.com",
                 "https://careers.smartrecruiters.com/Acme")
    job_id = _add_structured_job(
        sqlite_engine, 731, adapter="smartrecruiters", source="smartrecruiters",
        source_url="https://jobs.smartrecruiters.com/Acme/9",
        native_id="9", ats_id="9", ai_status="CYBER")
    _patch_fetcher(monkeypatch, lambda req: _FakeResponse(dict(SR_SECTIONS)))
    summary = asyncio.run(enrich_official_html_details(
        sqlite_engine, ScannerSettings(), limit=5, inter_job_wait_seconds=0))
    assert summary.updated_jobs == 1 and summary.failed_jobs == 0
    with Session(sqlite_engine) as session:
        row = session.get(SourceJob, job_id)
        assert "Build APIs." in row.detail_description
        assert "Write tests." in row.detail_description
        assert row.ai_status == "PENDING_AI"
        assert row.ai_last_error is None
        assert row.source_job_id == "9"  # identity unchanged


def test_identical_detail_does_not_requeue(
    sqlite_engine: Engine, monkeypatch,
) -> None:
    create_schema(sqlite_engine)
    _seed_portal(sqlite_engine, 741,
                 "careers.smartrecruiters.com",
                 "https://careers.smartrecruiters.com/Acme")
    job_id = _add_structured_job(
        sqlite_engine, 741, adapter="smartrecruiters", source="smartrecruiters",
        source_url="https://jobs.smartrecruiters.com/Acme/9",
        native_id="9", ats_id="9", ai_status="CYBER")
    handler = lambda req: _FakeResponse(dict(SR_SECTIONS))  # noqa: E731
    _patch_fetcher(monkeypatch, handler)
    asyncio.run(enrich_official_html_details(
        sqlite_engine, ScannerSettings(), limit=5, inter_job_wait_seconds=0))
    with Session(sqlite_engine) as session, session.begin():
        row = session.get(SourceJob, job_id)
        row.ai_status = "CYBER"  # simulate completed analysis
    summary = asyncio.run(enrich_official_html_details(
        sqlite_engine, ScannerSettings(), limit=5, inter_job_wait_seconds=0))
    assert summary.unchanged_jobs == 1 and summary.updated_jobs == 0
    with Session(sqlite_engine) as session:
        assert session.get(SourceJob, job_id).ai_status == "CYBER"  # no requeue


def test_qualifications_only_change_requeues(
    sqlite_engine: Engine, monkeypatch,
) -> None:
    create_schema(sqlite_engine)
    _seed_portal(sqlite_engine, 751,
                 "careers.smartrecruiters.com",
                 "https://careers.smartrecruiters.com/Acme")
    job_id = _add_structured_job(
        sqlite_engine, 751, adapter="smartrecruiters", source="smartrecruiters",
        source_url="https://jobs.smartrecruiters.com/Acme/9",
        native_id="9", ats_id="9", ai_status="CYBER")
    _patch_fetcher(monkeypatch, lambda req: _FakeResponse(dict(SR_SECTIONS)))
    asyncio.run(enrich_official_html_details(
        sqlite_engine, ScannerSettings(), limit=5, inter_job_wait_seconds=0))
    with Session(sqlite_engine) as session, session.begin():
        session.get(SourceJob, job_id).ai_status = "CYBER"
    changed = {"jobAd": {"sections": {
        "jobDescription": {"text": "<p>Build APIs.</p>"},
        "qualifications": {"text": "<p>Write tests AND docs.</p>"}}}}
    _patch_fetcher(monkeypatch, lambda req: _FakeResponse(changed))
    summary = asyncio.run(enrich_official_html_details(
        sqlite_engine, ScannerSettings(), limit=5, inter_job_wait_seconds=0))
    assert summary.updated_jobs == 1
    with Session(sqlite_engine) as session:
        row = session.get(SourceJob, job_id)
        assert row.ai_status == "PENDING_AI"
        assert "docs" in row.detail_description


def test_empty_detail_records_failure_without_store(
    sqlite_engine: Engine, monkeypatch,
) -> None:
    create_schema(sqlite_engine)
    _seed_portal(sqlite_engine, 761,
                 "careers.smartrecruiters.com",
                 "https://careers.smartrecruiters.com/Acme")
    job_id = _add_structured_job(
        sqlite_engine, 761, adapter="smartrecruiters", source="smartrecruiters",
        source_url="https://jobs.smartrecruiters.com/Acme/9",
        native_id="9", ats_id="9", ai_status="CYBER",
        raw_description="short")
    _patch_fetcher(monkeypatch, lambda req: _FakeResponse({"jobAd": {"sections": {}}}))
    summary = asyncio.run(enrich_official_html_details(
        sqlite_engine, ScannerSettings(), limit=5, inter_job_wait_seconds=0))
    assert summary.failed_jobs == 1 and summary.updated_jobs == 0
    with Session(sqlite_engine) as session:
        row = session.get(SourceJob, job_id)
        assert row.detail_description == ""  # catalog data untouched
        assert row.ai_status == "CYBER"  # no requeue on empty


def test_terminal_abort_on_circuit_breaker(
    sqlite_engine: Engine, monkeypatch,
) -> None:
    create_schema(sqlite_engine)
    _seed_portal(sqlite_engine, 771,
                 "careers.smartrecruiters.com",
                 "https://careers.smartrecruiters.com/Acme")
    for pid, jid in (("9", "9"), ("10", "10")):
        _add_structured_job(
            sqlite_engine, 771, adapter="smartrecruiters",
            source="smartrecruiters",
            source_url=f"https://jobs.smartrecruiters.com/Acme/{jid}",
            native_id=jid, ats_id=jid, ai_status="CYBER")

    def handler(request):
        raise HostCircuitOpenError("429 slows this host", attempts=())

    fakes = _patch_fetcher(monkeypatch, handler)
    summary = asyncio.run(enrich_official_html_details(
        sqlite_engine, ScannerSettings(), limit=5, inter_job_wait_seconds=0))
    assert summary.failed_jobs == 1
    assert len(fakes[0].requests) == 1  # second candidate never attempted


# ---------- B20: catalog scans fetch zero details ----------

def _scan_urls(adapter, target, handler):
    requested: list = []

    def recording(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return handler(request)

    async def run():
        fetcher = HttpFetcher(
            max_retries=0, per_domain_min_interval_seconds=0,
            jitter_seconds=0, resolve_dns=False,
            transport=httpx.MockTransport(recording),
        )
        async with fetcher:
            from research_agent.sources.base import PortalScanContext
            return await adapter.scan(
                target, PortalScanContext(fetcher=fetcher))

    asyncio.run(run())
    return requested


def _portal(url: str, family: str) -> PortalTarget:
    return PortalTarget(
        portal_id=1, jobs_search_url=url, normalized_jobs_url=url,
        host=httpx.URL(url).host, ats_families=(family,),
        ats_confidences=("Verified",))


def test_catalog_scans_issue_zero_detail_requests() -> None:
    wd = WorkdayAdapter()

    def wd_handler(req: httpx.Request) -> httpx.Response:
        if "cxs" not in str(req.url):
            return httpx.Response(
                200, text="var c={tenant: 'acme', siteId: 'AcmeSite'};",
                request=req)
        return httpx.Response(
            200, json={"total": 0, "jobPostings": []}, request=req)

    wd_urls = _scan_urls(
        wd, _portal("https://acme.wd3.myworkdayjobs.com/AcmeSite", "Workday"),
        wd_handler,
    )
    assert not [u for u in wd_urls if u.rstrip("/").endswith("/apply")]
    assert not [u for u in wd_urls if "/wday/cxs/" in u and "/jobs" not in u]

    sr = SmartRecruitersAdapter()
    sr_urls = _scan_urls(
        sr, _portal("https://careers.smartrecruiters.com/Acme", "SmartRecruiters"),
        lambda req: httpx.Response(
            200, json={"content": [], "totalFound": 0}, request=req),
    )
    assert not [
        u for u in sr_urls
        if "/postings/" in u.split("?")[0] and "limit=" not in u
    ]

    oc = OracleRecruitingCloudAdapter()
    oc_urls = _scan_urls(
        oc, _portal("https://x.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1",
                    "Oracle Recruiting Cloud"),
        lambda req: httpx.Response(
            200,
            text='<base data-apibaseurl="https://x.fa.oraclecloud.com" data-sitenumber="CX_1" href="/hcmUI/CandidateExperience/en/sites/CX_1">',
            request=req)
        if "hcmRestApi" not in str(req.url) else
        httpx.Response(
            200,
            json={"items": [{"TotalJobsCount": 0, "requisitionList": []}]},
            request=req),
    )
    assert not [u for u in oc_urls if "Details?finder=ById" in u]

    from research_agent.sources.declarative.adapter import (
        DeclarativeSourceAdapter,
        DeclarativeSourceBinding,
    )
    from research_agent.sources.declarative import adapter as _decl_mod
    import pathlib as _pl
    base_dir = _pl.Path(_decl_mod.__file__).resolve().parent
    decl = DeclarativeSourceAdapter(
        [DeclarativeSourceBinding("https://jobs.nvidia.com/careers", "specs/nvidia.json")],
        base_dir=base_dir,
    )
    decl_urls = _scan_urls(
        decl, _portal("https://jobs.nvidia.com/careers", "Eightfold"),
        lambda req: httpx.Response(
            200, json={"data": {"positions": [], "count": 0}}, request=req),
    )
    assert not [u for u in decl_urls if "position_details" in u]
