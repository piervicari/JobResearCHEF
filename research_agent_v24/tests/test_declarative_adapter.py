"""Offline Phase-2 tests: DeclarativeSourceAdapter as a registry sibling.

Everything here runs against httpx.MockTransport through the REAL
HttpFetcher: zero live HTTP, zero browser. Real wire shapes come from
the frozen runtime fixtures (Mercedes) or synthetic payloads that keep
the real protocol (Eightfold offset query / Beesite-style POST body —
asserted structurally, never named in the implementation).
"""
from __future__ import annotations

import asyncio
import copy
import json
from datetime import date, datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_agent.db.migrations import create_schema
from research_agent.db.models import (
    CanonicalJob,
    ClusterPortalMapping,
    CorporateCluster,
    ImportBatch,
    JobObservation,
    Portal,
    ScanRun,
    SourceJob,
)
from research_agent.pipeline.http import (
    FetchRequest,
    HostCircuitOpenError,
    HttpFetcher,
)
from research_agent.pipeline.lifecycle import process_scan_results
from research_agent.pipeline.payload import serialize_observation_payload
from research_agent.pipeline.scanner import PortalScanResult, ScanSummary
from research_agent.sources.ats.common import AdapterHttpError
from research_agent.sources.ats.registry import structured_adapter_registry
from research_agent.sources.base import (
    AdapterScanResult,
    PortalScanContext,
    PortalTarget,
    RawJob,
)
from research_agent.sources.declarative import (
    DeclarativeSourceAdapter,
    DeclarativeSourceBinding,
    load_declarative_adapter,
    normalized_job_to_raw_job,
)
from research_agent.sources.declarative import bridge as declarative_bridge
from research_agent.sources.declarative import executor as declarative_executor

DECLARATIVE_DIR = Path(__file__).resolve().parent.parent / "src" / "research_agent" / "sources" / "declarative"
SPECS_DIR = DECLARATIVE_DIR / "specs"

# Frozen offline fixtures from the runtime experiment (read-only).
# Repo root is JobResearCHEF/ = parents[2] of this file
# (tests -> research_agent_v24 -> JobResearCHEF).
_REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_FIXTURES = _REPO_ROOT / "runtime" / "fixtures"

MERCEDES_PORTAL = "https://jobs.mercedes-benz.com"
NVIDIA_PORTAL = "https://jobs.nvidia.com/careers"
MICROSOFT_PORTAL = "https://careers.microsoft.com"


def _payload_dict(job: RawJob) -> dict:
    assert job.raw_payload is not None
    assert isinstance(job.raw_payload, dict)
    return job.raw_payload  # type: ignore[return-value]


def _spec(name: str) -> dict:
    return json.loads((SPECS_DIR / name).read_text(encoding="utf-8"))


def _target(portal_url: str, portal_id: int = 1) -> PortalTarget:
    return PortalTarget(
        portal_id=portal_id,
        jobs_search_url=portal_url,
        normalized_jobs_url=portal_url,
        host=httpx.URL(portal_url).host,
        ats_families=(),
        ats_confidences=(),
    )


def _adapter() -> DeclarativeSourceAdapter:
    return load_declarative_adapter()


def _run_scan(adapter, target, handler, *, max_pages=30, max_jobs=500):
    requested: list[httpx.Request] = []

    def recording_handler(request: httpx.Request) -> httpx.Response:
        requested.append(request)
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
            context = PortalScanContext(
                fetcher=fetcher,
                max_pages_per_portal=max_pages,
                max_jobs_per_portal=max_jobs,
            )
            return await adapter.scan(target, context)

    return asyncio.run(run()), requested


# ---------- synthetic Eightfold-family catalog pages ----------

def _eightfold_item(index: int, *, with_description: bool = False) -> dict:
    item = {
        "id": f"JR-{index:05d}",
        "displayJobId": f"D-{index:05d}",
        "atsJobId": f"A-{index:05d}",
        "name": f"Security Engineer {index}",
        "department": "Engineering",
        "postedTs": 1756684800 + index,
        "locations": ["Santa Clara, California, United States of America"],
        "publicUrl": f"https://jobs.example.test/careers/job/JR-{index:05d}",
        "positionUserActions": {
            "applyAction": {"applyUrl": f"https://jobs.example.test/apply/JR-{index:05d}"}
        },
    }
    if with_description:
        item["jobDescription"] = f"<p>Own detection engineering for area {index}.</p>"
    return item


def _eightfold_handler(total: int, *, with_description: bool = False):
    def handler(request: httpx.Request) -> httpx.Response:
        query = dict(httpx.QueryParams(request.url.query))
        start = int(query.get("start", 0))
        items = [
            _eightfold_item(i, with_description=with_description)
            for i in range(start, min(start + 10, total))
        ]
        return httpx.Response(
            200,
            json={"data": {"positions": items, "count": total}},
            request=request,
        )

    return handler


# ============================================================
# Binding: exact match only, never heuristics (§21)
# ============================================================

def test_exact_binding_selects_declarative_adapter():
    registry = structured_adapter_registry(declarative_adapters=[_adapter()])
    selected = registry.select(_target(NVIDIA_PORTAL))
    assert isinstance(selected, DeclarativeSourceAdapter)


def test_unbound_portal_is_not_selected():
    registry = structured_adapter_registry(declarative_adapters=[_adapter()])
    assert registry.select(_target("https://jobs.unknown-example.test/openings")) is None


def test_similar_hostname_is_not_enough():
    registry = structured_adapter_registry(declarative_adapters=[_adapter()])
    assert registry.select(_target("https://jobs.nvidia.com/other-portal")) is None
    assert registry.select(_target("https://careers.nvidia.com/careers")) is None


def test_matching_ats_family_is_not_enough():
    registry = structured_adapter_registry(declarative_adapters=[_adapter()])
    target = PortalTarget(
        portal_id=1,
        jobs_search_url="https://jobs.other-example.test/search",
        normalized_jobs_url="https://jobs.other-example.test/search",
        host="jobs.other-example.test",
        ats_families=("Eightfold",),
        ats_confidences=("Verified",),
    )
    assert registry.select(target) is None


def test_matching_company_text_is_not_enough():
    registry = structured_adapter_registry(declarative_adapters=[_adapter()])
    target = PortalTarget(
        portal_id=1,
        jobs_search_url="https://nvidia-jobs.example.test/",
        normalized_jobs_url="https://nvidia-jobs.example.test/",
        host="nvidia-jobs.example.test",
        ats_families=(),
        ats_confidences=(),
    )
    assert registry.select(target) is None


def test_legacy_registry_behavior_unchanged_without_config():
    registry = structured_adapter_registry()
    assert registry.names == (
        "greenhouse",
        "google_careers_rpc",
        "lever",
        "ashby",
        "smartrecruiters",
        "radancy_talentbrew",
        "successfactors_rmk",
        "workday",
        "phenom",
        "oracle_recruiting_cloud",
        "avature",
        "teamtailor",
        "workable",
    )
    assert isinstance(registry.select(_target(NVIDIA_PORTAL)), type(None))


def _family_target(portal_url: str, family: str, portal_id: int = 1) -> PortalTarget:
    return PortalTarget(
        portal_id=portal_id,
        jobs_search_url=portal_url,
        normalized_jobs_url=portal_url,
        host=httpx.URL(portal_url).host,
        ats_families=(family,),
        ats_confidences=("Verified",),
    )


def test_bound_portal_beats_legacy_family_heuristic():
    """Conflict A: the bound Microsoft portal also carries a family marker
    that SuccessFactorsRmkAdapter.supports matches (substring, any URL).
    First-match order must still select the explicit binding."""
    from research_agent.sources.ats.successfactors import SuccessFactorsRmkAdapter

    heuristic = _family_target(MICROSOFT_PORTAL, "SuccessFactors Recruiting Marketing")
    assert SuccessFactorsRmkAdapter().supports(heuristic) is True
    registry = structured_adapter_registry(declarative_adapters=[_adapter()])
    assert isinstance(registry.select(heuristic), DeclarativeSourceAdapter)


def test_unbound_portal_with_same_marker_stays_legacy():
    """Conflict B: same family marker but no binding → legacy adapter."""
    from research_agent.sources.ats.successfactors import SuccessFactorsRmkAdapter

    target = _family_target("https://jobs.other-example.test/search", "SuccessFactors Recruiting Marketing")
    registry = structured_adapter_registry(declarative_adapters=[_adapter()])
    assert isinstance(registry.select(target), SuccessFactorsRmkAdapter)


def test_exact_binding_beats_direct_host_legacy_match():
    """Conflict C: even a legacy adapter matching host+family loses to the
    exact binding (precedence is structural, not company-specific)."""
    from research_agent.sources.ats.greenhouse import GreenhouseAdapter

    target = PortalTarget(
        portal_id=1,
        jobs_search_url=MICROSOFT_PORTAL,
        normalized_jobs_url=MICROSOFT_PORTAL,
        host="boards.greenhouse.io",
        ats_families=("Greenhouse",),
        ats_confidences=("Verified",),
    )
    assert GreenhouseAdapter().supports(target) is True
    registry = structured_adapter_registry(declarative_adapters=[_adapter()])
    assert isinstance(registry.select(target), DeclarativeSourceAdapter)


def test_duplicate_binding_is_rejected():
    with pytest.raises(ValueError):
        DeclarativeSourceAdapter(
            [
                DeclarativeSourceBinding(NVIDIA_PORTAL, "specs/nvidia.json"),
                DeclarativeSourceBinding(NVIDIA_PORTAL, "specs/nvidia.json"),
            ],
            base_dir=DECLARATIVE_DIR,
        )


# ============================================================
# Mercedes catalog scan with the REAL frozen fixture (§18)
# ============================================================

def _real_mercedes_items(count: int) -> list:
    fixture = json.loads((RUNTIME_FIXTURES / "mercedes_catalog_page.json").read_text(encoding="utf-8"))
    return fixture["SearchResult"]["SearchResultItems"][:count]


def _mercedes_handler(items: list, total: int):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        body = json.loads(request.content.decode("utf-8"))
        first_item = body["SearchParameters"]["FirstItem"]
        assert body["SearchCriteria"] == []
        if first_item == 1:
            page_items = items
        else:
            page_items = []
        return httpx.Response(
            200,
            json={
                "SearchResult": {
                    "SearchResultCount": len(page_items),
                    "SearchResultCountAll": total,
                    "SearchResultItems": page_items,
                }
            },
            request=request,
        )

    return handler


def test_mercedes_catalog_scan_real_fixture():
    adapter = _adapter()
    # The frozen offline fixture carries exactly one real catalog item;
    # the scan serves it with a synthetic total=1 (real protocol shape).
    items = _real_mercedes_items(3)
    assert len(items) == 1
    result, requested = _run_scan(adapter, _target(MERCEDES_PORTAL), _mercedes_handler(items, 1))
    assert isinstance(result, AdapterScanResult)
    # First page + terminal empty-after-total probe, both POST.
    assert len(requested) == 2
    assert all(request.method == "POST" for request in requested)
    assert len(result.jobs) == 1
    assert result.is_complete_snapshot is True

    first = result.jobs[0]
    assert first.source == "declarative:mercedes-benz"
    assert first.source_job_id == "mer000484n"
    assert first.title == "Executive, Digital Apps & Online Platforms"
    # Responsibilities + qualifications both present in the semantic text.
    assert "Lead the regional digital apps and online platforms portfolio" in first.description
    assert "10+ years in digital product leadership." in first.description
    assert "\n\nQualifications:\n" in first.description
    # ... while the payload keeps them as separate structured fields.
    payload = _payload_dict(first)
    assert "Lead the regional digital apps" in str(payload["description"])
    assert "10+ years in digital product leadership." in str(payload["qualifications"])
    assert payload["department"] == "Brand & Communications Strategy"
    assert payload["organization"] == "Mercedes-Benz Taiwan Ltd."
    assert payload["detail_complete"] is True
    declarative_meta = payload["_declarative"]
    assert isinstance(declarative_meta, dict)
    assert declarative_meta["company_id"] == "mercedes-benz"
    assert declarative_meta["source_platform"] == payload["source_platform"]
    native = payload["_source_native"]
    assert isinstance(native, dict)
    # Native item is the unwrapped descriptor (extract_page unwraps the
    # single-key envelope before extraction and conversion).
    assert native["PositionID"] == "mer000484n"
    # Location + apply URL from the real item.
    assert "Taipei" in first.location
    assert first.apply_url.startswith("https://")
    # No detail endpoint exists for this spec family: nothing to hydrate.
    assert not [request for request in requested if "position_details" in str(request.url)]


def test_mercedes_source_identity_is_namespaced_without_schema_version():
    adapter = _adapter()
    items = _real_mercedes_items(1)
    result, _ = _run_scan(adapter, _target(MERCEDES_PORTAL), _mercedes_handler(items, 1))
    assert result.jobs[0].source == "declarative:mercedes-benz"
    assert "v0.1" not in result.jobs[0].source
    assert "source_spec" not in result.jobs[0].source


# ============================================================
# NVIDIA catalog scan: no N+1 detail fetch (§19)
# ============================================================

def test_nvidia_catalog_scan_no_detail_fetch():
    adapter = _adapter()
    result, requested = _run_scan(adapter, _target(NVIDIA_PORTAL), _eightfold_handler(25))
    assert len(result.jobs) == 25
    assert result.is_complete_snapshot is True
    # Exactly the 3 catalog pages (offsets 0/10/20): no per-job detail calls.
    assert len(requested) == 3
    assert not [request for request in requested if "position_details" in str(request.url)]
    first = result.jobs[0]
    assert first.source == "declarative:nvidia"
    assert first.source_job_id == "JR-00000"
    assert first.title == "Security Engineer 0"
    assert first.description == ""  # description_in_catalog=false: cheap catalog scan
    assert first.raw_payload is not None
    assert first.raw_payload["detail_complete"] is False
    assert first.company == "NVIDIA"
    assert "Santa Clara" in first.location
    assert first.apply_url == "https://jobs.example.test/apply/JR-00000"
    assert first.posted_at is not None


def test_microsoft_shares_the_identical_execution_path():
    adapter = _adapter()
    microsoft_target = _target(MICROSOFT_PORTAL, portal_id=2)
    nvidia_target = _target(NVIDIA_PORTAL, portal_id=1)
    assert adapter.supports(microsoft_target)
    assert adapter.supports(nvidia_target)
    microsoft_result, microsoft_requested = _run_scan(
        adapter, microsoft_target, _eightfold_handler(12)
    )
    assert len(microsoft_result.jobs) == 12
    assert microsoft_result.is_complete_snapshot is True
    assert len(microsoft_requested) == 2
    assert not [request for request in microsoft_requested if "position_details" in str(request.url)]
    assert microsoft_result.jobs[0].source == "declarative:microsoft"
    assert "microsoft.eightfold.ai" in str(microsoft_requested[0].url)


def test_render_detail_fetch_helper_is_explicit_and_not_used_by_scan():
    adapter = _adapter()
    target = _target(NVIDIA_PORTAL)
    fetch_request = adapter.render_detail_fetch(target, "JR-00042")
    assert isinstance(fetch_request, FetchRequest)
    assert "position_id=JR-00042" in fetch_request.url
    assert fetch_request.method == "GET"


def _requested_starts(requested: list[httpx.Request]) -> list[int]:
    starts = []
    for request in requested:
        query = dict(httpx.QueryParams(request.url.query))
        starts.append(int(query.get("start", -1)))
    return starts


def test_exact_boundary_total_20_probes_once_then_complete():
    """total=20, page_size=10: two full data pages cannot satisfy
    last_page_shorter_than_page_size alone, so exactly one terminal
    probe (start=20, empty) is required — and sufficient."""
    adapter = _adapter()
    result, requested = _run_scan(adapter, _target(NVIDIA_PORTAL), _eightfold_handler(20))
    assert _requested_starts(requested) == [0, 10, 20]
    assert len(result.jobs) == 20
    assert result.is_complete_snapshot is True


def test_exact_boundary_total_10_probes_once_then_complete():
    adapter = _adapter()
    result, requested = _run_scan(adapter, _target(NVIDIA_PORTAL), _eightfold_handler(10))
    assert _requested_starts(requested) == [0, 10]
    assert len(result.jobs) == 10
    assert result.is_complete_snapshot is True


def test_partial_final_page_needs_no_probe():
    """total=12: the partial final page (2 items) already satisfies the
    rule — no unnecessary empty probe may follow it."""
    adapter = _adapter()
    result, requested = _run_scan(adapter, _target(NVIDIA_PORTAL), _eightfold_handler(12))
    assert _requested_starts(requested) == [0, 10]
    assert len(result.jobs) == 12
    assert result.is_complete_snapshot is True


def test_traversal_completeness_ignores_unique_job_count():
    """INVARIANT (§5): catalog traversal completeness != downstream
    unique-job count. Upstream may repeat a stable ID across pages
    (e.g. unexercised language variants would); the adapter must NOT
    dedup silently — history counts traversed ITEMS, and completeness
    is decided on history, never on unique RawJobs. Any future
    stable-ID dedup must happen downstream of this accounting."""
    def handler(request: httpx.Request) -> httpx.Response:
        query = dict(httpx.QueryParams(request.url.query))
        start = int(query.get("start", 0))
        # Second page repeats the first page's stable IDs verbatim.
        items = [_eightfold_item(i % 10) for i in range(start, min(start + 10, 20))]
        return httpx.Response(
            200, json={"data": {"positions": items, "count": 20}}, request=request
        )

    adapter = _adapter()
    result, requested = _run_scan(adapter, _target(NVIDIA_PORTAL), handler)
    assert _requested_starts(requested) == [0, 10, 20]
    assert len(result.jobs) == 20  # traversed items, NOT unique ids
    assert len({job.source_job_id for job in result.jobs}) == 10
    assert result.is_complete_snapshot is True


def test_conditional_probe_on_generic_synthetic_spec():
    """Same conditional-probe semantics on a non-Eightfold-shaped spec:
    zero-based offset in query, string ids, no detail block."""
    spec = _spec("nvidia.json")
    spec = copy.deepcopy(spec)
    spec["company"] = {"id": "synthetic", "name": "Synthetic Co"}
    spec["paging"]["page_size"] = 5
    spec["extraction"]["page_wrapper"] = {"items": "rows", "total": "total"}
    spec["extraction"]["item_path"] = "rows"
    spec["extraction"]["total_path"] = "total"
    spec["extraction"]["stable_id_path"] = "uid"
    spec["extraction"]["secondary_id_paths"] = []
    spec["extraction"]["title_path"] = "title"
    spec["extraction"]["department_path"] = None
    spec["extraction"]["organization_path"] = None
    spec["extraction"]["publication_date_path"] = None
    spec["extraction"]["expiration_date_path"] = None
    spec["extraction"]["official_url_path"] = None
    spec["extraction"]["official_url_template"] = "https://syn.example.test/j/{{stable_id}}"
    spec["extraction"]["apply_url_path"] = None
    spec["extraction"]["language_path"] = None
    spec["extraction"]["locations"] = {"path": "loc", "shape": "list_of_strings"}
    spec["extraction"]["description"] = {"path": "body", "shape": "string", "strip_html": True}

    def handler(request: httpx.Request) -> httpx.Response:
        query = dict(httpx.QueryParams(request.url.query))
        start = int(query.get("start", 0))
        rows = [
            {"uid": f"S-{i}", "title": f"Role {i}", "loc": ["Nowhere"]}
            for i in range(start, min(start + 5, 10))
        ]
        return httpx.Response(200, json={"rows": rows, "total": 10}, request=request)

    adapter = DeclarativeSourceAdapter(
        [DeclarativeSourceBinding("https://syn.example.test/jobs", "specs/nvidia.json")],
        base_dir=DECLARATIVE_DIR,
    )
    # Swap in the synthetic spec for the bound URL (same object identity
    # the loader built; keeps the test offline and binding-exact).
    adapter._specs["https://syn.example.test/jobs"] = spec
    target = _target("https://syn.example.test/jobs")
    result, requested = _run_scan(adapter, target, handler)
    # total=10 with page_size=5 is an exact boundary: two full data pages
    # plus the single conditional terminal probe (start=10, empty).
    assert _requested_starts(requested) == [0, 5, 10]
    assert [job.source_job_id for job in result.jobs] == [f"S-{i}" for i in range(10)]
    assert {job.source for job in result.jobs} == {"declarative:synthetic"}
    assert result.is_complete_snapshot is True


# ============================================================
# Safety preflight: fail closed, never silently ignored (§2)
# ============================================================

def test_scan_applies_spec_safety_limits(tmp_path):
    """scan() wires spec safety into the generic funnel: a spec budget of
    max_requests_per_run=1 stops the catalog after one request with partial
    results kept, complete_snapshot=false and an explicit warning."""
    from research_agent.sources.declarative.adapter import (
        DeclarativeSourceAdapter,
        DeclarativeSourceBinding,
    )

    base = json.loads((DECLARATIVE_DIR / "specs" / "nvidia.json").read_text(encoding="utf-8"))
    spec = copy.deepcopy(base)
    spec["safety"]["max_requests_per_run"] = 1
    spec["safety"]["max_consecutive_errors"] = 0
    tmp_spec = tmp_path / "budget_spec.json"
    tmp_spec.write_text(json.dumps(spec), encoding="utf-8")
    adapter = DeclarativeSourceAdapter(
        [DeclarativeSourceBinding(NVIDIA_PORTAL, tmp_spec.name)],
        base_dir=tmp_path,
    )
    result, requested = _run_scan(adapter, _target(NVIDIA_PORTAL), _eightfold_handler(25))
    assert len(requested) == 1
    assert len(result.jobs) == 10
    assert result.is_complete_snapshot is False
    assert any("budget" in warning for warning in result.warnings)


def test_mercedes_preflight_passes_with_enforced_long_pause():
    """Long pauses are now ENFORCED_PER_SCAN (context mechanism wired by
    the adapter), so even strict settings reach SAFE_TO_RUN on Mercedes."""
    from research_agent.sources.declarative import safety as safety_module

    spec = _spec("mercedes.json")
    strict = safety_module.EffectiveScannerSafety(
        per_domain_concurrency=1,
        per_domain_min_interval_seconds=1.2,
        max_requests_per_run=600,
        max_requests_per_host_per_run=30,
        max_retries=1,
    )
    result = safety_module.preflight_safety(spec, strict)
    assert result.verdict == "SAFE_TO_RUN"
    assert result.reasons == ()


def test_default_scanner_settings_pass_nvidia_preflight():
    """Default ScannerSettings (interval 1.0s, 2 retries) used to be weaker
    than the NVIDIA spec (max 1 retry). Retry ceiling and interval floor are
    now enforced per-request by the adapter wiring, so defaults are SAFE."""
    from research_agent.config import ScannerSettings
    from research_agent.sources.declarative import safety as safety_module

    spec = _spec("nvidia.json")
    effective = safety_module.effective_safety_from_settings(ScannerSettings())
    result = safety_module.preflight_safety(spec, effective)
    assert result.verdict == "SAFE_TO_RUN"
    assert result.reasons == ()


def test_nonsequential_settings_still_block_preflight():
    """sequential_only is the one requirement no per-request override may
    loosen: per_domain_concurrency=2 must stay SCANNER_SETTINGS_TOO_PERMISSIVE."""
    from research_agent.config import ScannerSettings
    from research_agent.sources.declarative import safety as safety_module

    spec = _spec("nvidia.json")
    settings = ScannerSettings(per_domain_concurrency=2)
    effective = safety_module.effective_safety_from_settings(settings)
    result = safety_module.preflight_safety(spec, effective)
    assert result.verdict == "SCANNER_SETTINGS_TOO_PERMISSIVE"
    assert any("sequential_only" in reason for reason in result.reasons)


def test_strict_settings_pass_supported_requirements():
    from research_agent.sources.declarative import safety as safety_module

    spec = copy.deepcopy(_spec("nvidia.json"))
    # Neutralize the two NOT_CURRENTLY_SUPPORTED requirements to prove
    # the mechanism itself can reach SAFE_TO_RUN.
    spec["safety"]["long_pause_every_n_requests"] = 0
    spec["safety"]["long_pause_seconds"] = 0
    spec["safety"]["max_consecutive_errors"] = 0
    strict = safety_module.EffectiveScannerSafety(
        per_domain_concurrency=1,
        per_domain_min_interval_seconds=0.5,
        max_requests_per_run=600,
        max_requests_per_host_per_run=30,
        max_retries=1,
    )
    result = safety_module.preflight_safety(spec, strict)
    assert result.verdict == "SAFE_TO_RUN"
    assert result.reasons == ()


def test_unsupported_active_requirement_blocks_before_any_http():
    """assert_safe_to_run raises without touching the network on a genuinely
    unsupported setup: per_domain_concurrency=2 violates sequential_only.
    The preflight is pure (no fetcher, no transport), so 'before HTTP' is
    structural, not a race."""
    from research_agent.sources.declarative import safety as safety_module

    spec = _spec("microsoft.json")
    nonsequential = safety_module.EffectiveScannerSafety(
        per_domain_concurrency=2,
        per_domain_min_interval_seconds=5.0,
        max_requests_per_run=10,
        max_requests_per_host_per_run=5,
        max_retries=0,
    )
    with pytest.raises(safety_module.UnsafeToRunError):
        safety_module.assert_safe_to_run(spec, nonsequential)


def test_adapter_preflight_delegates_to_bound_spec():
    """Raise-None contract: non-sequential settings raise UnsafeToRunError
    for the bound spec (verdict-object diagnostics stay available via
    safety.preflight_safety, covered by the module-level tests above);
    default settings pass without raising."""
    adapter = _adapter()
    from research_agent.sources.declarative import safety as safety_module

    nonsequential = safety_module.EffectiveScannerSafety(
        per_domain_concurrency=2,
        per_domain_min_interval_seconds=5.0,
        max_requests_per_run=10,
        max_requests_per_host_per_run=5,
        max_retries=0,
    )
    with pytest.raises(safety_module.UnsafeToRunError) as raised:
        adapter.preflight(_target(NVIDIA_PORTAL), nonsequential)
    assert "SCANNER_SETTINGS_TOO_PERMISSIVE" in str(raised.value)

    from research_agent.config import ScannerSettings

    assert adapter.preflight(_target(NVIDIA_PORTAL), ScannerSettings()) is None


# ============================================================
# Qualifications semantics: composition + hash (Phase 2, mandatory)
# ============================================================

def _converter_job(*, description: str, qualifications: str) -> RawJob:
    spec = _spec("mercedes.json")
    normalized = {
        "source_job_id": "x1",
        "source_secondary_ids": ["9"],
        "title": "Analyst",
        "department": "IT",
        "organization": "Example Org",
        "locations": ["Taipei"],
        "publication_date": "2026-09-04",
        "official_url": "https://jobs.example.test/x1",
        "apply_url": "",
        "description": description,
        "qualifications": qualifications,
        "detail_complete": bool(description and qualifications),
        "company_id": "mercedes-benz",
        "source_platform": "beesite",
        "source_last_seen_at": "2026-09-06T00:00:00+00:00",
    }
    return normalized_job_to_raw_job(spec, normalized, native_item={"native": True})


def test_qualifications_composed_into_legacy_description():
    job = _converter_job(description="Own the platform.", qualifications="5+ years on call.")
    assert job.description == "Own the platform.\n\nQualifications:\n5+ years on call."


def test_empty_qualifications_never_duplicate_heading():
    job = _converter_job(description="Own the platform.", qualifications="")
    assert job.description == "Own the platform."
    assert "Qualifications" not in job.description


def test_payload_preserves_structure_separately():
    job = _converter_job(description="Own the platform.", qualifications="5+ years on call.")
    payload = _payload_dict(job)
    assert payload["description"] == "Own the platform."
    assert payload["qualifications"] == "5+ years on call."
    assert payload["department"] == "IT"
    assert payload["organization"] == "Example Org"
    assert payload["locations"] == ["Taipei"]
    declarative_meta = payload["_declarative"]
    assert isinstance(declarative_meta, dict)
    assert declarative_meta["detail_complete"] is True
    assert payload["_source_native"] == {"native": True}


def test_qualification_only_change_alters_legacy_payload_hash():
    before = _converter_job(description="Own the platform.", qualifications="5+ years on call.")
    after = _converter_job(description="Own the platform.", qualifications="6+ years on call.")
    assert after.description != before.description
    _, sha_before = serialize_observation_payload(
        before, company_id="CG-1", company_name="Example", adapter="declarative"
    )
    _, sha_after = serialize_observation_payload(
        after, company_id="CG-1", company_name="Example", adapter="declarative"
    )
    assert sha_before != sha_after


def test_apply_url_falls_back_to_official_url():
    job = _converter_job(description="d", qualifications="")
    assert job.apply_url == "https://jobs.example.test/x1"


# ============================================================
# Completeness matrix (§13/§14/§15/§23)
# ============================================================

def test_page_cap_truncates_snapshot():
    adapter = _adapter()
    result, _ = _run_scan(
        adapter, _target(NVIDIA_PORTAL), _eightfold_handler(25), max_pages=1
    )
    assert len(result.jobs) == 10
    assert result.is_complete_snapshot is False
    assert any("safety cap" in warning for warning in result.warnings)


def test_job_cap_truncates_snapshot():
    adapter = _adapter()
    result, _ = _run_scan(
        adapter, _target(NVIDIA_PORTAL), _eightfold_handler(25), max_jobs=5
    )
    assert len(result.jobs) == 5
    assert result.is_complete_snapshot is False
    assert any("job cap" in warning for warning in result.warnings)


def test_empty_page_before_total_is_not_complete():
    def handler(request: httpx.Request) -> httpx.Response:
        query = dict(httpx.QueryParams(request.url.query))
        start = int(query.get("start", 0))
        items = [] if start >= 10 else [_eightfold_item(i) for i in range(10)]
        return httpx.Response(
            200, json={"data": {"positions": items, "count": 25}}, request=request
        )

    adapter = _adapter()
    result, _ = _run_scan(adapter, _target(NVIDIA_PORTAL), handler)
    assert len(result.jobs) == 10
    assert result.is_complete_snapshot is False
    assert any("empty page" in warning for warning in result.warnings)


def test_changing_total_marks_snapshot_not_authoritative():
    totals = [25, 30]

    def handler(request: httpx.Request) -> httpx.Response:
        query = dict(httpx.QueryParams(request.url.query))
        start = int(query.get("start", 0))
        total = totals[0] if start == 0 else totals[1]
        items = [_eightfold_item(i) for i in range(start, min(start + 10, total))]
        return httpx.Response(
            200, json={"data": {"positions": items, "count": total}}, request=request
        )

    adapter = _adapter()
    result, _ = _run_scan(adapter, _target(NVIDIA_PORTAL), handler)
    assert result.is_complete_snapshot is False
    assert any("total changed" in warning for warning in result.warnings)


def test_http_403_stops_immediately_with_partial_kept():
    """HTTP 403 stops the scan at the first page: zero further requests,
    partial jobs preserved, complete_snapshot=false, explicit warning.
    The fetcher still blocks the host (unchanged circuit-breaker path)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, content=b"denied", request=request)

    adapter = _adapter()
    from research_agent.pipeline.http import HttpFetcher

    requested: list[httpx.Request] = []

    def recording_handler(request: httpx.Request) -> httpx.Response:
        requested.append(request)
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
            context = PortalScanContext(
                fetcher=fetcher,
                max_pages_per_portal=30,
                max_jobs_per_portal=500,
            )
            result = await adapter.scan(_target(NVIDIA_PORTAL), context)
            return result, fetcher

    result, fetcher = asyncio.run(run())
    assert len(requested) == 1
    assert result.is_complete_snapshot is False
    assert any("403" in warning for warning in result.warnings)
    assert fetcher.blocked_hosts, "403 must still block the host in the fetcher"


def test_http_429_opens_circuit_without_retry():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(429, headers={"Retry-Alt": "0"}, request=request)

    adapter = _adapter()
    with pytest.raises(HostCircuitOpenError):
        _run_scan(adapter, _target(NVIDIA_PORTAL), handler)
    assert len(calls) == 1


# ============================================================
# Static genericity scan: core implementation names nothing (§17)
# ============================================================

def test_core_implementation_names_no_source():
    for filename in ("adapter.py", "bridge.py", "executor.py"):
        source = (DECLARATIVE_DIR / filename).read_text(encoding="utf-8").lower()
        for token in (
            "mercedes",
            "nvidia",
            "microsoft",
            "eightfold",
            "beesite",
            "greenhouse",
            "apple",
            "amazon",
            "google",
        ):
            assert token not in source, f"{filename} mentions source token {token!r}"
        words = set(source.replace("_", " ").split())
        # 'meta' only as a whole word: must not match 'method'/'metadata'.
        assert "meta" not in words, f"{filename} mentions source token 'meta'"


# ============================================================
# v0.1 off-by-one BUGFIX regression (§24)
# ============================================================

def _zero_based_spec() -> dict:
    spec = _spec("nvidia.json")
    spec = copy.deepcopy(spec)
    spec["paging"]["page_size"] = 10
    spec["paging"]["first_page_value"] = 0
    spec["completeness"]["rules"] = [
        {"name": "next_offset_ge_total", "kind": "next_offset_ge_total"}
    ]
    return spec


def test_boundary_total_needs_no_phantom_data_page():
    spec = _zero_based_spec()
    history = [{"page_value": 0, "items_count": 10, "total": 10}]
    complete, _ = declarative_executor.evaluate_completeness(spec, history)
    assert complete is True


def test_iterator_and_evaluator_agree_on_data_pages():
    spec = _zero_based_spec()
    for total in (0, 1, 9, 10, 11, 20, 21, 24, 30):
        iterator_offsets = list(declarative_executor.pagination_iterator(spec, total))
        complete, _ = declarative_executor.evaluate_completeness(
            spec,
            [
                {
                    "page_value": offset,
                    "items_count": 10,
                    "total": total,
                }
                for offset in iterator_offsets
            ],
        )
        assert complete is True, f"iterator/evaluator disagree at total={total}"


def test_single_item_catalog_needs_data_page_plus_probe():
    # total == first (one-based): exactly one item at the first offset.
    # The max(0, ...) guard matters here: without it the single real
    # data page is skipped and the probe lands on top of it.
    spec = _spec("mercedes.json")
    assert list(declarative_executor.pagination_iterator(spec, 1)) == [1, 51]
    history = [
        {"page_value": 1, "items_count": 1, "total": 1},
        {"page_value": 51, "items_count": 0, "total": 1},
    ]
    complete, _ = declarative_executor.evaluate_completeness(spec, history)
    assert complete is True


# ============================================================
# Bridge merge regressions: urllib.parse cleanup (§4)
# ============================================================

def test_bridge_preserves_fragment_repeats_unicode_and_bool():
    rendered = {
        "method": "GET",
        "url": "https://jobs.example.test/search?content=true#results",
        "headers": {"Accept": "application/json"},
        "query": {"tag": ["a", "b"], "city": "München", "remote": True, "blank": ""},
        "body": {},
    }
    fetch_request = declarative_bridge.to_fetch_request(rendered)
    assert isinstance(fetch_request, FetchRequest)
    url = fetch_request.url
    assert url.startswith("https://jobs.example.test/search?content=true&")
    assert "tag=a&tag=b" in url
    assert "M%C3%BCnchen" in url
    assert "remote=true" in url
    assert "blank=" in url
    assert url.endswith("#results")


# ============================================================
# Lifecycle integration: declarative jobs persist end to end (§27)
# ============================================================

def _seed_registry(engine: Engine, *, company: str) -> int:
    create_schema(engine)
    with Session(engine) as session, session.begin():
        batch = ImportBatch(
            source_kind="test",
            source_filename="fixture.csv",
            source_path="fixture.csv",
            source_sha256="a" * 64,
            source_version="test",
            status="COMPLETED",
        )
        session.add(batch)
        session.flush()
        cluster = CorporateCluster(
            corporate_cluster_id="CG-D",
            representative_canonical_employer=company,
            canonical_employers_json=json.dumps([company]),
            parent_groups_json="[]",
            entity_classes_json='["Employer Candidate"]',
            eligibility_values_json='["Yes"]',
            sectors_json='["Technology"]',
            discovery_geographies_json='["Italy"]',
            org_types_json='["Company"]',
            record_count=1,
            has_primary_scan_eligibility=True,
            active_in_master=True,
            import_batch_id=batch.id,
        )
        session.add(cluster)
        portal = Portal(
            normalized_jobs_url=MERCEDES_PORTAL,
            jobs_search_url=MERCEDES_PORTAL,
            scheme="https",
            host="jobs.mercedes-benz.com",
            ats_families_json='["declarative"]',
            ats_confidences_json='["Verified"]',
            metadata_conflict=False,
            cluster_count=1,
            active_in_registry=True,
            health_state="UNKNOWN",
            consecutive_failures=0,
            consecutive_empty_scans=0,
            import_batch_id=batch.id,
        )
        session.add(portal)
        session.flush()
        session.add(
            ClusterPortalMapping(
                corporate_cluster_id=cluster.corporate_cluster_id,
                portal_id=portal.id,
                resolved_corporate_website="https://example.test",
                resolved_careers_landing_url="https://example.test/careers",
                source_jobs_search_url=portal.jobs_search_url,
                portal_scope="Global",
                ats_family="declarative",
                ats_confidence="Verified",
                portal_resolution_status="VERIFIED_WAVE_TEST",
                portal_verification_url=portal.jobs_search_url,
                portal_verified_date=date(2026, 8, 30),
                resolution_parent_override="",
                resolution_wave="TEST",
                source_record_count=1,
                import_batch_id=batch.id,
            )
        )
        session.flush()
        return portal.id


def _scan_summary_for(
    engine: Engine, *, portal_id: int, jobs: tuple[RawJob, ...], complete_snapshot: bool = True
) -> ScanSummary:
    now = datetime.now().astimezone()
    with Session(engine) as session, session.begin():
        run = ScanRun(
            source="test",
            status="COMPLETED",
            started_at=now,
            finished_at=now,
            portal_count=1,
            success_count=1,
            failure_count=0,
            jobs_discovered=len(jobs),
            pipeline_status="NOT_PROCESSED",
        )
        session.add(run)
        session.flush()
        portal = session.get(Portal, portal_id)
        assert portal is not None
        target = PortalTarget(
            portal_id=portal.id,
            jobs_search_url=portal.jobs_search_url,
            normalized_jobs_url=portal.normalized_jobs_url,
            host=portal.host,
            ats_families=("declarative",),
            ats_confidences=("Verified",),
        )
        result = PortalScanResult(
            target=target,
            adapter="declarative",
            status="SUCCESS",
            started_at=now,
            finished_at=now,
            jobs=jobs,
            fetch_attempts=(),
            retry_count=0,
            final_http_status=200,
            response_sha256=None,
            cache_hit=False,
            complete_snapshot=complete_snapshot,
            error_type=None,
            error_message=None,
        )
        return ScanSummary(
            scan_run_id=run.id,
            status=run.status,
            portal_count=1,
            success_count=1,
            failure_count=0,
            request_count=0,
            retry_count=0,
            jobs_discovered=len(jobs),
            portal_results=(result,),
        )


def _declarative_raw_job(*, qualifications: str) -> RawJob:
    return _converter_job(
        description="Own the regional platform portfolio.",
        qualifications=qualifications,
    )


def test_lifecycle_persists_declarative_job_with_semantic_text(sqlite_engine: Engine):
    portal_id = _seed_registry(sqlite_engine, company="Mercedes-Benz")
    raw = _declarative_raw_job(qualifications="5+ years on call.")
    summary = process_scan_results(
        sqlite_engine, _scan_summary_for(sqlite_engine, portal_id=portal_id, jobs=(raw,))
    )
    assert summary.observations == 1
    with Session(sqlite_engine) as session:
        source = session.scalar(select(SourceJob))
        assert source is not None
        assert source.source == "declarative:mercedes-benz"
        assert source.source_job_id == "x1"
        assert source.raw_title == "Analyst"
        assert "Own the regional platform portfolio." in source.raw_description
        assert "5+ years on call." in source.raw_description
        assert "\n\nQualifications:\n" in source.raw_description
        assert source.apply_url == "https://jobs.example.test/x1"
        assert source.ats_job_id == "9"
        observation = session.scalar(select(JobObservation))
        assert observation is not None and observation.payload_changed


def test_qualification_only_change_marks_payload_changed(sqlite_engine: Engine):
    portal_id = _seed_registry(sqlite_engine, company="Mercedes-Benz")
    first = _scan_summary_for(
        sqlite_engine,
        portal_id=portal_id,
        jobs=(_declarative_raw_job(qualifications="5+ years on call."),),
    )
    process_scan_results(sqlite_engine, first)
    second = _scan_summary_for(
        sqlite_engine,
        portal_id=portal_id,
        jobs=(_declarative_raw_job(qualifications="6+ years on call."),),
    )
    process_scan_results(sqlite_engine, second)
    with Session(sqlite_engine) as session:
        observations = session.scalars(select(JobObservation).order_by(JobObservation.id)).all()
        assert len(observations) == 2
        assert observations[0].payload_changed is True
        assert observations[1].payload_changed is True
        source = session.scalar(select(SourceJob))
        assert source is not None
        assert "6+ years on call." in source.raw_description


def test_ai_status_not_requeued_by_lifecycle_on_payload_change(sqlite_engine: Engine):
    """EXISTING LEGACY FINDING (see §28): process_scan_results computes
    payload_changed on every JobObservation but _update_source_job never
    resets ai_status to PENDING_AI. Only the separate
    discovery.persist_scan_discoveries path requeues. This test pins the
    current behaviour so the future LLM-on-change requirement can see it.
    """
    portal_id = _seed_registry(sqlite_engine, company="Mercedes-Benz")
    process_scan_results(
        sqlite_engine,
        _scan_summary_for(
            sqlite_engine,
            portal_id=portal_id,
            jobs=(_declarative_raw_job(qualifications="5+ years on call."),),
        ),
    )
    with Session(sqlite_engine) as session, session.begin():
        source = session.scalar(select(SourceJob))
        assert source is not None
        source.ai_status = "CYBER"  # pretend the LLM already analyzed this job
    process_scan_results(
        sqlite_engine,
        _scan_summary_for(
            sqlite_engine,
            portal_id=portal_id,
            jobs=(_declarative_raw_job(qualifications="6+ years on call."),),
        ),
    )
    with Session(sqlite_engine) as session:
        source = session.scalar(select(SourceJob))
        observation = session.scalars(
            select(JobObservation).order_by(JobObservation.id.desc())
        ).first()
        assert source is not None and observation is not None
        assert observation.payload_changed is True  # change WAS detected ...
        assert source.ai_status == "CYBER"  # ... but no AI requeue happened
