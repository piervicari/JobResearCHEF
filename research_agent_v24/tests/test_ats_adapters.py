import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from research_agent.pipeline.http import (
    AccessChallengeError,
    HostCircuitOpenError,
    HttpFetcher,
    RequestBudgetExceededError,
    TooManyRedirectsError,
    UnsafeDestinationError,
)
from research_agent.sources.ats.ashby import AshbyAdapter
from research_agent.sources.ats.avature import AvatureAdapter
from research_agent.sources.ats.common import AdapterSchemaError
from research_agent.sources.ats.greenhouse import GreenhouseAdapter
from research_agent.sources.ats.lever import LeverAdapter
from research_agent.sources.ats.oracle import OracleRecruitingCloudAdapter
from research_agent.sources.ats.phenom import PhenomAdapter
from research_agent.sources.ats.radancy import RadancyAdapter
from research_agent.sources.ats.registry import structured_adapter_registry
from research_agent.sources.ats.smartrecruiters import SmartRecruitersAdapter
from research_agent.sources.ats.successfactors import SuccessFactorsRmkAdapter
from research_agent.sources.ats.workday import WorkdayAdapter
from research_agent.sources.base import (
    AdapterScanResult,
    PortalScanContext,
    PortalTarget,
    ScanRequestBudgetExceeded,
)


def _target(url: str, ats_family: str, portal_id: int = 1) -> PortalTarget:
    host = httpx.URL(url).host
    return PortalTarget(
        portal_id=portal_id,
        jobs_search_url=url,
        normalized_jobs_url=url,
        host=host,
        ats_families=(ats_family,),
        ats_confidences=("Verified",),
    )


def _fixture(fixtures: Path, name: str) -> object:
    return json.loads((fixtures / name).read_text(encoding="utf-8"))


def _scan(adapter: object, target: PortalTarget, payload: object) -> tuple[object, list[str]]:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, json=payload, request=request)

    async def run():
        fetcher = HttpFetcher(
            max_retries=0,
            per_domain_min_interval_seconds=0,
            jitter_seconds=0,
            resolve_dns=False,
            transport=httpx.MockTransport(handler),
        )
        async with fetcher:
            return await adapter.scan(target, PortalScanContext(fetcher))

    return asyncio.run(run()), requested


@pytest.fixture()
def fixtures() -> Path:
    return Path(__file__).parent / "fixtures"


def test_greenhouse_adapter_uses_public_board_api(fixtures: Path) -> None:
    adapter = GreenhouseAdapter()
    target = _target("https://job-boards.greenhouse.io/example", "Greenhouse")
    result, requested = _scan(adapter, target, _fixture(fixtures, "greenhouse_jobs.json"))

    assert requested == ["https://boards-api.greenhouse.io/v1/boards/example/jobs?content=true"]
    assert len(result.jobs) == 1
    job = result.jobs[0]
    assert job.source_job_id == "101"
    assert job.title == "Junior Security Analyst"
    assert job.location == "Milan, Italy"
    assert job.requisition_id == "SEC-101"
    assert result.is_complete_snapshot is True


def test_greenhouse_does_not_claim_unverified_embedded_portal() -> None:
    target = _target("https://example.com/careers", "Greenhouse embedded")
    assert GreenhouseAdapter().supports(target) is False


def test_greenhouse_empty_board_is_valid_complete_snapshot() -> None:
    # {"jobs": []} on a valid envelope means zero active jobs, not a parser
    # failure (unknown boards answer 404 via require_success). Live empty
    # board still unobserved; this pins the code path the gate depends on.
    adapter = GreenhouseAdapter()
    target = _target("https://job-boards.greenhouse.io/example", "Greenhouse")
    result, requested = _scan(adapter, target, {"jobs": []})
    assert isinstance(result, AdapterScanResult)

    assert requested == ["https://boards-api.greenhouse.io/v1/boards/example/jobs?content=true"]
    assert result.jobs == ()
    assert result.is_complete_snapshot is True
    assert any("zero active jobs" in warning for warning in result.warnings)


def test_lever_adapter_uses_public_postings_api(fixtures: Path) -> None:
    adapter = LeverAdapter()
    target = _target("https://jobs.lever.co/example", "Lever")
    result, requested = _scan(adapter, target, _fixture(fixtures, "lever_jobs.json"))

    assert requested == ["https://api.lever.co/v0/postings/example?mode=json&skip=0&limit=100"]
    job = result.jobs[0]
    assert job.source_job_id == "lever-101"
    assert job.employment_type == "Intern"
    assert job.workplace_type == "hybrid"
    assert job.location == "London, UK | Remote - UK"


def test_ashby_adapter_uses_public_posting_api_and_skips_unlisted(fixtures: Path) -> None:
    adapter = AshbyAdapter()
    target = _target("https://jobs.ashbyhq.com/example", "Ashby")
    result, requested = _scan(adapter, target, _fixture(fixtures, "ashby_jobs.json"))

    assert requested == ["https://api.ashbyhq.com/posting-api/job-board/example?includeCompensation=true"]
    assert len(result.jobs) == 1
    job = result.jobs[0]
    assert job.title == "Cybersecurity Graduate"
    assert job.posted_at is not None
    assert job.posted_at.isoformat() == "2026-08-21T09:30:00+00:00"


def test_smartrecruiters_adapter_uses_public_posting_api(fixtures: Path) -> None:
    adapter = SmartRecruitersAdapter()
    target = _target("https://careers.smartrecruiters.com/Example", "SmartRecruiters")
    result, requested = _scan(adapter, target, _fixture(fixtures, "smartrecruiters_jobs.json"))

    assert requested == [
        "https://api.smartrecruiters.com/v1/companies/Example/postings?limit=100&offset=0"
    ]
    job = result.jobs[0]
    assert job.title == "Information Security Intern"
    assert job.company == "Example Ltd"
    assert job.location == "Milan, Lombardy, IT"
    assert job.workplace_type == "remote"
    assert job.apply_url == job.source_url


def test_successfactors_rmk_adapter_parses_and_follows_server_pagination(
    fixtures: Path,
) -> None:
    adapter = SuccessFactorsRmkAdapter()
    target = _target(
        "https://jobs.example.test/",
        "SAP SuccessFactors Recruiting Marketing-style",
    )
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        fixture = (
            "successfactors_search_page_2.html"
            if request.url.params.get("startrow") == "25"
            else "successfactors_search_page_1.html"
        )
        return httpx.Response(
            200,
            text=(fixtures / fixture).read_text(encoding="utf-8"),
            headers={"Content-Type": "text/html"},
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
            return await adapter.scan(target, PortalScanContext(fetcher))

    result = asyncio.run(run())
    assert len(result.jobs) == 2
    assert result.jobs[0].source_job_id == "1001"
    assert result.jobs[0].location == "Rome, Italy"
    assert result.jobs[1].title == "Cybersecurity Intern"
    assert result.is_complete_snapshot is True
    assert len(requested) == 2
    assert "startrow=0" in requested[0]
    assert "startrow=25" in requested[1]


def test_successfactors_rmk_routing_requires_explicit_family_marker() -> None:
    verified = _target(
        "https://jobs.example.test/",
        "SAP SuccessFactors Recruiting Marketing-style",
    )
    ambiguous = _target("https://jobs.example.test/", "Atos: SuccessFactors-style")

    assert SuccessFactorsRmkAdapter().supports(verified) is True
    assert SuccessFactorsRmkAdapter().supports(ambiguous) is False


def test_successfactors_honors_per_portal_page_budget(fixtures: Path) -> None:
    adapter = SuccessFactorsRmkAdapter()
    target = _target(
        "https://jobs.example.test/",
        "SAP SuccessFactors Recruiting Marketing-style",
    )
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(
            200,
            text=(fixtures / "successfactors_search_page_1.html").read_text(
                encoding="utf-8"
            ),
            headers={"Content-Type": "text/html"},
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
            context = PortalScanContext(fetcher, max_pages_per_portal=1)
            return await adapter.scan(target, context)

    result = asyncio.run(run())
    assert len(requested) == 1
    assert result.is_complete_snapshot is False
    assert result.warnings == (
        "SuccessFactors pagination stopped at safety cap of 1 pages",
    )


def test_workday_adapter_reads_bootstrap_and_posts_paginated_jobs(fixtures: Path) -> None:
    adapter = WorkdayAdapter()
    adapter.page_size = 1
    target = _target(
        "https://example.wd5.myworkdayjobs.com/ExampleCareers",
        "Workday",
    )
    requested: list[tuple[str, str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            requested.append((request.method, str(request.url), None))
            return httpx.Response(
                200,
                text=(fixtures / "workday_landing.html").read_text(encoding="utf-8"),
                request=request,
            )
        body = json.loads(request.content)
        requested.append((request.method, str(request.url), body))
        fixture = "workday_jobs_page_2.json" if body["offset"] == 1 else "workday_jobs_page_1.json"
        return httpx.Response(200, json=_fixture(fixtures, fixture), request=request)

    async def run():
        fetcher = HttpFetcher(
            max_retries=0,
            per_domain_min_interval_seconds=0,
            jitter_seconds=0,
            resolve_dns=False,
            transport=httpx.MockTransport(handler),
        )
        async with fetcher:
            return await adapter.scan(target, PortalScanContext(fetcher))

    result = asyncio.run(run())
    assert result.is_complete_snapshot is True
    assert result.warnings == ("Workday total changed during pagination: 2 -> 0",)
    assert [job.source_job_id for job in result.jobs] == ["REQ-1001", "REQ-1002"]
    assert result.jobs[0].apply_url == (
        "https://example.wd5.myworkdayjobs.com/ExampleCareers/"
        "job/Italy/Junior-Security-Analyst_REQ-1001"
    )
    assert [method for method, _, _ in requested] == ["GET", "POST", "POST"]
    assert requested[1][2]["offset"] == 0
    assert requested[2][2]["offset"] == 1


def test_workday_requisition_prefers_id_shape_over_badge_labels() -> None:
    """Cohort-60 evidence: Intel/Thales lead bulletFields with badge labels
    ("Spotlight Job", "Regular Employee"), which collapsed dozens of jobs
    onto one native id. Requisition shapes win; anything else falls back to
    the stable externalPath."""
    adapter = WorkdayAdapter()

    def parse(bullets, external_path="/job/X/Role_JR1"):
        return adapter._parse_job(
            {"title": "Role", "externalPath": external_path,
             "bulletFields": bullets},
            site_url="https://example.wd5.myworkdayjobs.com/Site",
            index=0,
        )

    assert parse(["Spotlight Job", "JR0286861"]).source_job_id == "JR0286861"
    assert parse(["Regular Employee", "R0334457", "10 - INDUSTRY"]).source_job_id == "R0334457"
    assert parse(["R14702"]).source_job_id == "R14702"
    assert parse(["J0107014"]).source_job_id == "J0107014"
    assert parse(["2618439"]).source_job_id == "2618439"
    assert parse(["REQ-1001"]).source_job_id == "REQ-1001"
    assert parse(["Night Shift"]).source_job_id == "/job/X/Role_JR1"
    assert parse([]).source_job_id == "/job/X/Role_JR1"


def test_workday_routing_requires_direct_host_and_unambiguous_family() -> None:
    direct = _target(
        "https://example.wd5.myworkdayjobs.com/ExampleCareers",
        "Workday Recruiting",
    )
    branded = _target(
        "https://careers.example.test/search-results",
        "Phenom frontend + Workday employment system",
    )

    assert WorkdayAdapter().supports(direct) is True
    assert WorkdayAdapter().supports(branded) is False


def test_workday_skips_malformed_posting_without_losing_valid_jobs(
    fixtures: Path,
) -> None:
    adapter = WorkdayAdapter()
    target = _target(
        "https://example.wd5.myworkdayjobs.com/ExampleCareers",
        "Workday",
    )
    payload = _fixture(fixtures, "workday_jobs_page_1.json")
    assert isinstance(payload, dict)
    payload["total"] = 2
    payload["jobPostings"].append({"title": "missing path"})

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                text=(fixtures / "workday_landing.html").read_text(encoding="utf-8"),
                request=request,
            )
        return httpx.Response(200, json=payload, request=request)

    async def run():
        fetcher = HttpFetcher(
            max_retries=0,
            per_domain_min_interval_seconds=0,
            jitter_seconds=0,
            resolve_dns=False,
            transport=httpx.MockTransport(handler),
        )
        async with fetcher:
            return await adapter.scan(target, PortalScanContext(fetcher))

    result = asyncio.run(run())
    assert [job.source_job_id for job in result.jobs] == ["REQ-1001"]
    assert result.is_complete_snapshot is False
    assert result.warnings == (
        "Workday jobPostings[1] is missing title or externalPath; skipped",
    )


def _workday_synthetic_board(fixtures: Path, *, page_size: int, total: int):
    """Serve a fully synthetic Workday board from memory (zero live wires).

    Every page reports the SAME stable total; each posting carries a
    requisition-shaped bullet id so identity stays exercisable.
    """
    adapter = WorkdayAdapter()
    adapter.page_size = page_size
    landing_text = (fixtures / "workday_landing.html").read_text(encoding="utf-8")

    def posting(index: int) -> dict:
        return {
            "title": f"Role {index}",
            "externalPath": f"/job/Site/Role-{index}_REQ-{9000 + index}",
            "locationsText": "Rome, Italy",
            "postedOn": "Posted Today",
            "bulletFields": [f"REQ-{9000 + index}"],
        }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, text=landing_text, request=request)
        offset = json.loads(request.content)["offset"]
        page = [posting(i) for i in range(offset, min(offset + page_size, total))]
        return httpx.Response(200, json={"total": total, "jobPostings": page},
                              request=request)

    return adapter, handler


def _run_workday_scan(adapter, target, handler, *, max_pages, max_jobs,
                      host_budget=1000, run_budget=1000):
    async def run():
        fetcher = HttpFetcher(
            max_retries=0,
            per_domain_min_interval_seconds=0,
            jitter_seconds=0,
            resolve_dns=False,
            max_requests_per_host_per_run=host_budget,
            max_requests_per_run=run_budget,
            transport=httpx.MockTransport(handler),
        )
        async with fetcher:
            context = PortalScanContext(
                fetcher, max_pages_per_portal=max_pages,
                max_jobs_per_portal=max_jobs,
            )
            return await adapter.scan(target, context)

    return asyncio.run(run())


def test_workday_uncapped_catalog_stays_complete(fixtures: Path) -> None:
    """A. Normal board below the provider cap, naturally exhausted → TRUE."""
    adapter, handler = _workday_synthetic_board(fixtures, page_size=20, total=44)
    target = _target(
        "https://example.wd5.myworkdayjobs.com/ExampleCareers",
        "Workday",
    )
    result = _run_workday_scan(adapter, target, handler, max_pages=100,
                               max_jobs=5000)
    assert len(result.jobs) == 44
    assert result.is_complete_snapshot is True
    assert all(w != WorkdayAdapter.CAPPED_TOTAL_WARNING for w in result.warnings)


def test_workday_default_context_stays_conservative(fixtures: Path) -> None:
    """Normal runs keep the conservative page ceiling: a 3000-job board
    under the default 30-page context stops bounded at 600 jobs."""
    adapter, handler = _workday_synthetic_board(fixtures, page_size=20, total=3000)
    target = _target(
        "https://example.wd5.myworkdayjobs.com/ExampleCareers",
        "Workday",
    )
    result = _run_workday_scan(adapter, target, handler, max_pages=30,
                               max_jobs=5000)
    assert len(result.jobs) == 600
    assert result.is_complete_snapshot is False


def test_workday_explicit_high_page_budget_not_clamped(fixtures: Path) -> None:
    """An explicitly authorized 250-page context traverses a 3000-job
    uncapped board past the old 100-page adapter ceiling → TRUE."""
    adapter, handler = _workday_synthetic_board(fixtures, page_size=20, total=3000)
    target = _target(
        "https://example.wd5.myworkdayjobs.com/ExampleCareers",
        "Workday",
    )
    result = _run_workday_scan(adapter, target, handler, max_pages=250,
                               max_jobs=5000)
    assert len(result.jobs) == 3000
    assert result.is_complete_snapshot is True


def test_workday_explicit_pages_do_not_bypass_hard_stops(fixtures: Path) -> None:
    """Explicit page authorization does not bypass the host wire budget or
    the per-portal job cap."""
    from research_agent.pipeline.http import RequestBudgetExceededError

    adapter, handler = _workday_synthetic_board(fixtures, page_size=20, total=3000)
    target = _target(
        "https://example.wd5.myworkdayjobs.com/ExampleCareers",
        "Workday",
    )
    with pytest.raises(RequestBudgetExceededError):
        _run_workday_scan(adapter, target, handler, max_pages=250,
                          max_jobs=5000, host_budget=5)
    capped = _run_workday_scan(adapter, target, handler, max_pages=250,
                               max_jobs=50)
    assert len(capped.jobs) == 50
    assert capped.is_complete_snapshot is False


def test_workday_page_budget_exhaustion_stays_incomplete(fixtures: Path) -> None:
    """A 3000-job board under a 2-page context → jobs kept, FALSE."""
    adapter, handler = _workday_synthetic_board(fixtures, page_size=20, total=3000)
    target = _target(
        "https://example.wd5.myworkdayjobs.com/ExampleCareers",
        "Workday",
    )
    result = _run_workday_scan(adapter, target, handler, max_pages=2,
                               max_jobs=5000)
    assert len(result.jobs) == 40
    assert result.is_complete_snapshot is False


def test_workday_suspicious_cap_catalog_is_never_complete(fixtures: Path) -> None:
    """B. Canonical total == provider cap (2000) with full apparent traversal
    MUST NOT complete: upstream may hold more than the cap reports."""
    adapter, handler = _workday_synthetic_board(fixtures, page_size=20,
                                                total=2000)
    target = _target(
        "https://example.wd5.myworkdayjobs.com/ExampleCareers",
        "Workday",
    )
    result = _run_workday_scan(adapter, target, handler, max_pages=100,
                               max_jobs=5000)
    assert len(result.jobs) == 2000
    assert result.is_complete_snapshot is False
    assert WorkdayAdapter.CAPPED_TOTAL_WARNING in result.warnings
    # Identity intact on the capped board: requisition-shaped native ids.
    assert result.jobs[0].source_job_id == "REQ-9000"
    assert result.jobs[-1].source_job_id == "REQ-10999"


def test_workday_bounded_scan_stays_incomplete(fixtures: Path) -> None:
    """C. Budget-capped scan of a capped board remains FALSE (both guards)."""
    adapter, handler = _workday_synthetic_board(fixtures, page_size=20,
                                                total=2000)
    target = _target(
        "https://example.wd5.myworkdayjobs.com/ExampleCareers",
        "Workday",
    )
    result = _run_workday_scan(adapter, target, handler, max_pages=2,
                               max_jobs=5000)
    assert len(result.jobs) == 40
    assert result.is_complete_snapshot is False


def test_workday_identity_fix_survives_cap_guard() -> None:
    """D. Badge-label fallback (cohort-60 P0 fix) is untouched by the guard."""
    adapter = WorkdayAdapter()
    job = adapter._parse_job(
        {"title": "Role", "externalPath": "/job/X/Role_JR1",
         "bulletFields": ["Regular Employee", "R0334457"]},
        site_url="https://example.wd5.myworkdayjobs.com/Site",
        index=0,
    )
    assert job.source_job_id == "R0334457"


class _FacetBoard:
    """In-memory Workday CXS mock routed by (appliedFacets, offset).

    Zero live wires. Unknown routes answer HTTP 400 (loud test bug).
    """

    def __init__(self, fixtures: Path, page_size: int = 20) -> None:
        self.landing_text = (fixtures / "workday_landing.html").read_text(
            encoding="utf-8"
        )
        self.page_size = page_size
        self.routes: dict[frozenset, tuple[int, list, list]] = {}
        self.fail_routes: set[frozenset] = set()
        self.raw_overrides: dict[tuple[frozenset, int], tuple[int, object]] = {}
        self.raise_overrides: dict[tuple[frozenset, int], Exception] = {}
        self.bodies: list[dict] = []

    @staticmethod
    def posting(index: int) -> dict:
        return {
            "title": f"Role {index}",
            "externalPath": f"/job/Site/Role-{index}_REQ-{9000 + index}",
            "locationsText": "Rome, Italy",
            "postedOn": "Posted Today",
            "bulletFields": [f"REQ-{9000 + index}"],
        }

    @staticmethod
    def facet(dimension: str, values: list[tuple[str, int]]) -> dict:
        return {
            "facetParameter": dimension,
            "values": [{"id": vid, "count": count} for vid, count in values],
        }

    @staticmethod
    def key(applied: dict) -> frozenset:
        return frozenset((facet, tuple(values)) for facet, values in applied.items())

    def add(self, applied: dict, total: int, postings: list, facets: list) -> None:
        self.routes[self.key(applied)] = (total, postings, facets)

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, text=self.landing_text, request=request)
        body = json.loads(request.content)
        self.bodies.append(body)
        route = self.key(body.get("appliedFacets") or {})
        raised = self.raise_overrides.get((route, body["offset"]))
        if raised is not None:
            raise raised
        override = self.raw_overrides.get((route, body["offset"]))
        if override is not None:
            status, payload = override
            if isinstance(payload, bytes):
                return httpx.Response(status, content=payload, request=request)
            return httpx.Response(status, json=payload, request=request)
        if route in self.fail_routes or route not in self.routes:
            return httpx.Response(400, text="unknown test route", request=request)
        total, postings, facets = self.routes[route]
        offset = body["offset"]
        page = postings[offset:offset + self.page_size]
        return httpx.Response(
            200,
            json={"total": total, "jobPostings": page, "facets": facets},
            request=request,
        )


def _run_facet_board(board: _FacetBoard, *, max_pages: int, max_jobs: int,
                     host_budget: int = 1000, run_budget: int = 1000,
                     max_consecutive_errors: int | None = None):
    adapter = WorkdayAdapter()
    adapter.page_size = board.page_size
    target = _target(
        "https://example.wd5.myworkdayjobs.com/ExampleCareers",
        "Workday",
    )

    async def run():
        fetcher = HttpFetcher(
            max_retries=0,
            per_domain_min_interval_seconds=0,
            jitter_seconds=0,
            resolve_dns=False,
            max_requests_per_host_per_run=host_budget,
            max_requests_per_run=run_budget,
            transport=httpx.MockTransport(board.handler),
        )
        async with fetcher:
            context = PortalScanContext(
                fetcher, max_pages_per_portal=max_pages,
                max_jobs_per_portal=max_jobs,
                max_consecutive_errors=max_consecutive_errors,
            )
            return await adapter.scan(target, context)

    return asyncio.run(run())


def test_workday_max_consecutive_errors_aborts_siblings(fixtures: Path) -> None:
    """A. Consecutive-failure stop during subdivision propagates; sibling C
    never requested; the adapter control flow stops (not just later wire
    refusal)."""
    from research_agent.sources.base import MaxConsecutiveErrorsExceeded

    board = _three_branch_board(fixtures)
    board.raise_overrides[(_FacetBoard.key({"jobFamilyGroup": ["B"]}), 0)] = (
        TooManyRedirectsError("redirect loop in test", attempts=())
    )
    with pytest.raises(MaxConsecutiveErrorsExceeded):
        _run_facet_board(board, max_pages=100, max_jobs=5000,
                         max_consecutive_errors=1)
    applied = _applied_at_offset_zero(board)
    assert {"jobFamilyGroup": ["A"]} in applied
    assert {"jobFamilyGroup": ["C"]} not in applied


def test_workday_unsafe_destination_aborts_siblings(fixtures: Path) -> None:
    """B. Public-boundary violation is structural, never a normal branch
    condition: propagates, sibling C never requested."""
    board = _three_branch_board(fixtures)
    board.raise_overrides[(_FacetBoard.key({"jobFamilyGroup": ["B"]}), 0)] = (
        UnsafeDestinationError("outside public boundary in test", attempts=())
    )
    with pytest.raises(UnsafeDestinationError):
        _run_facet_board(board, max_pages=100, max_jobs=5000)
    applied = _applied_at_offset_zero(board)
    assert {"jobFamilyGroup": ["A"]} in applied
    assert {"jobFamilyGroup": ["C"]} not in applied


def test_workday_scan_request_budget_stays_bounded() -> None:
    """C. ScanRequestBudgetExceeded is explicitly NOT a hard abort:
    _paginate_branch keeps partial jobs and reports incomplete."""
    from research_agent.sources.ats.workday import WorkdayAdapter as WDAdapter

    async def run():
        adapter = WDAdapter()

        async def exploding_fetch(request):
            raise ScanRequestBudgetExceeded("per-scan wire budget spent in test")

        stub = SimpleNamespace(fetch=exploding_fetch)
        first_postings = [
            {"title": f"Role {i}", "externalPath": f"/job/S/Role-{i}_REQ-{i}",
             "bulletFields": [f"REQ-{i}"]}
            for i in range(20)
        ]
        warnings: list = []
        jobs, completed = await adapter._paginate_branch(
            stub,  # type: ignore[arg-type]  # minimal fetch-only stub
            "https://example.test/jobs", "https://example.test/Site",
            {}, ({"total": 40, "jobPostings": first_postings},
                 first_postings, 40),
            [10], warnings,
        )
        return jobs, completed, warnings

    jobs, completed, warnings = asyncio.run(run())
    assert len(jobs) == 20
    assert completed is False
    assert WorkdayAdapter.BRANCH_FAILED_WARNING in warnings
    assert ScanRequestBudgetExceeded not in WorkdayAdapter._HARD_ABORT_ERRORS


def test_workday_tiny_facet_cover_is_not_complete(fixtures: Path) -> None:
    """Coverage-gap repro: advertised 40+20=60 << capped root 2000.

    Traversing every advertised facet value is NOT proof the capped root
    was fully covered (value lists may be truncated; jobs may lack values;
    root total itself is capped) → jobs kept, complete FALSE."""
    board = _FacetBoard(fixtures)
    board.add({}, 2000, [_FacetBoard.posting(900 + i) for i in range(20)],
              [_FacetBoard.facet("jobFamilyGroup", [("A", 40), ("B", 20)])])
    board.add({"jobFamilyGroup": ["A"]}, 40,
              [_FacetBoard.posting(100 + i) for i in range(40)], [])
    board.add({"jobFamilyGroup": ["B"]}, 20,
              [_FacetBoard.posting(200 + i) for i in range(20)], [])

    result = _run_facet_board(board, max_pages=100, max_jobs=5000)

    assert len(result.jobs) == 60
    assert result.is_complete_snapshot is False
    assert WorkdayAdapter.COVERAGE_UNPROVEN_WARNING in result.warnings


def test_workday_subdivided_union_kept_bounded_without_proof(fixtures: Path) -> None:
    """Root total=2000 → one branch per jobFamilyGroup value → union kept,
    but coverage unproven (advertised 60 << capped 2000) → FALSE."""
    board = _FacetBoard(fixtures)
    root_postings = [_FacetBoard.posting(i) for i in range(20)]
    postings_a = [_FacetBoard.posting(100 + i) for i in range(40)]
    postings_b = [_FacetBoard.posting(200 + i) for i in range(20)]
    board.add({}, 2000, root_postings,
              [_FacetBoard.facet("jobFamilyGroup", [("A", 40), ("B", 20)])])
    board.add({"jobFamilyGroup": ["A"]}, 40, postings_a, [])
    board.add({"jobFamilyGroup": ["B"]}, 20, postings_b, [])

    result = _run_facet_board(board, max_pages=100, max_jobs=5000)

    assert len(result.jobs) == 60
    assert result.is_complete_snapshot is False
    assert WorkdayAdapter.SUBDIVISION_ACTIVATED_WARNING in result.warnings
    assert WorkdayAdapter.COVERAGE_INCOMPLETE_WARNING in result.warnings
    assert WorkdayAdapter.COVERAGE_UNPROVEN_WARNING in result.warnings
    assert WorkdayAdapter.CAPPED_TOTAL_WARNING in result.warnings
    applied = [body["appliedFacets"] for body in board.bodies if body["offset"] == 0]
    assert {"jobFamilyGroup": ["A"]} in applied
    assert {"jobFamilyGroup": ["B"]} in applied


def test_workday_nested_subdivision_stays_bounded(fixtures: Path) -> None:
    """Root capped → first-dimension branch still capped → second dimension
    resolves pagination, but coverage remains unproven → jobs kept, FALSE."""
    board = _FacetBoard(fixtures)
    board.add({}, 2000, [_FacetBoard.posting(i) for i in range(20)],
              [_FacetBoard.facet("jobFamilyGroup", [("A", 2000), ("B", 20)])])
    board.add({"jobFamilyGroup": ["A"]}, 2000,
              [_FacetBoard.posting(100 + i) for i in range(20)],
              [_FacetBoard.facet("timeType", [("FT", 30), ("PT", 20)])])
    board.add({"jobFamilyGroup": ["B"]}, 20,
              [_FacetBoard.posting(200 + i) for i in range(20)], [])
    board.add({"jobFamilyGroup": ["A"], "timeType": ["FT"]}, 30,
              [_FacetBoard.posting(300 + i) for i in range(30)], [])
    board.add({"jobFamilyGroup": ["A"], "timeType": ["PT"]}, 20,
              [_FacetBoard.posting(400 + i) for i in range(20)], [])

    result = _run_facet_board(board, max_pages=100, max_jobs=5000)

    assert len(result.jobs) == 70
    assert result.is_complete_snapshot is False
    assert WorkdayAdapter.COVERAGE_INCOMPLETE_WARNING in result.warnings
    assert WorkdayAdapter.COVERAGE_UNPROVEN_WARNING in result.warnings
    assert WorkdayAdapter.CAPPED_TOTAL_WARNING in result.warnings


def test_workday_overlapping_branches_deduplicate(fixtures: Path) -> None:
    """Same job in two branches persists once (JRC identity dedup), and the
    overlap itself is evidence against partition-completeness → FALSE."""
    board = _FacetBoard(fixtures)
    shared = [_FacetBoard.posting(i) for i in range(20)]
    board.add({}, 2000, [_FacetBoard.posting(900 + i) for i in range(20)],
              [_FacetBoard.facet("jobFamilyGroup", [("A", 20), ("B", 20)])])
    board.add({"jobFamilyGroup": ["A"]}, 20, shared, [])
    board.add({"jobFamilyGroup": ["B"]}, 20, shared, [])

    result = _run_facet_board(board, max_pages=100, max_jobs=5000)

    assert len(result.jobs) == 20
    assert len({job.source_job_id for job in result.jobs}) == 20
    assert result.is_complete_snapshot is False
    assert WorkdayAdapter.COVERAGE_UNPROVEN_WARNING in result.warnings


def test_workday_child_count_mismatch_is_flagged(fixtures: Path) -> None:
    """Branch paginates cleanly but recovers 25 jobs against advertised 40 →
    contradiction flagged, jobs kept, FALSE."""
    board = _FacetBoard(fixtures)
    board.add({}, 2000, [_FacetBoard.posting(900 + i) for i in range(20)],
              [_FacetBoard.facet("jobFamilyGroup", [("A", 40), ("B", 20)])])
    board.add({"jobFamilyGroup": ["A"]}, 25,
              [_FacetBoard.posting(100 + i) for i in range(25)], [])
    board.add({"jobFamilyGroup": ["B"]}, 20,
              [_FacetBoard.posting(200 + i) for i in range(20)], [])

    result = _run_facet_board(board, max_pages=100, max_jobs=5000)

    assert len(result.jobs) == 45
    assert result.is_complete_snapshot is False
    assert "disagrees with advertised facet count" in " ".join(result.warnings)
    assert WorkdayAdapter.COVERAGE_UNPROVEN_WARNING in result.warnings


def _run_subdivide(board: _FacetBoard, *, max_budget: int = 100):
    """Call _subdivide directly on the root filter state.

    Observes the resolution BOOLEAN itself (not just warnings/complete),
    proving contradictions structurally poison the proof chain."""

    adapter = WorkdayAdapter()
    adapter.page_size = board.page_size
    api_url = "https://example.wd5.myworkdayjobs.com/wday/cxs/Tenant/Site/jobs"
    site_url = "https://example.wd5.myworkdayjobs.com/Site"

    async def run():
        fetcher = HttpFetcher(
            max_retries=0,
            per_domain_min_interval_seconds=0,
            jitter_seconds=0,
            resolve_dns=False,
            max_requests_per_host_per_run=1000,
            max_requests_per_run=1000,
            transport=httpx.MockTransport(board.handler),
        )
        async with fetcher:
            context = PortalScanContext(
                fetcher, max_pages_per_portal=100,
                max_jobs_per_portal=5000,
            )
            first = await adapter._fetch_jobs_page(context, api_url, {}, 0)
            collected: dict = {}
            warnings: list = []
            resolved = await adapter._subdivide(
                context, api_url, site_url, {}, first,
                [max_budget], set(), collected, warnings,
            )
            return resolved, collected, warnings

    return asyncio.run(run())


def test_workday_c1_contradiction_poisons_resolution(fixtures: Path) -> None:
    """C1 structural: advertised 60 << parent 2000 → resolution FALSE even
    though every child paginates cleanly; jobs still collected."""
    board = _FacetBoard(fixtures)
    board.add({}, 2000, [_FacetBoard.posting(900 + i) for i in range(20)],
              [_FacetBoard.facet("jobFamilyGroup", [("A", 40), ("B", 20)])])
    board.add({"jobFamilyGroup": ["A"]}, 40,
              [_FacetBoard.posting(100 + i) for i in range(40)], [])
    board.add({"jobFamilyGroup": ["B"]}, 20,
              [_FacetBoard.posting(200 + i) for i in range(20)], [])

    resolved, collected, warnings = _run_subdivide(board)

    assert resolved is False
    assert len(collected) == 60
    assert WorkdayAdapter.COVERAGE_INCOMPLETE_WARNING in warnings


def test_workday_c2_mismatch_poisons_resolution(fixtures: Path) -> None:
    """C2 structural: clean child total 25 vs advertised 40 → that proof
    path FALSE; sibling jobs still collected."""
    board = _FacetBoard(fixtures)
    board.add({}, 2000, [_FacetBoard.posting(900 + i) for i in range(20)],
              [_FacetBoard.facet("jobFamilyGroup", [("A", 40), ("B", 20)])])
    board.add({"jobFamilyGroup": ["A"]}, 25,
              [_FacetBoard.posting(100 + i) for i in range(25)], [])
    board.add({"jobFamilyGroup": ["B"]}, 20,
              [_FacetBoard.posting(200 + i) for i in range(20)], [])

    resolved, collected, warnings = _run_subdivide(board)

    assert resolved is False
    assert len(collected) == 45
    assert "disagrees with advertised facet count" in " ".join(warnings)


def test_workday_nested_contradiction_propagates_to_root(fixtures: Path) -> None:
    """Nested C1 (timeType 30+20=50 << capped branch 2000) propagates all
    the way up: root resolution FALSE, all discovered jobs kept."""
    board = _FacetBoard(fixtures)
    board.add({}, 2000, [_FacetBoard.posting(i) for i in range(20)],
              [_FacetBoard.facet("jobFamilyGroup", [("A", 2000), ("B", 20)])])
    board.add({"jobFamilyGroup": ["A"]}, 2000,
              [_FacetBoard.posting(100 + i) for i in range(20)],
              [_FacetBoard.facet("timeType", [("FT", 30), ("PT", 20)])])
    board.add({"jobFamilyGroup": ["B"]}, 20,
              [_FacetBoard.posting(200 + i) for i in range(20)], [])
    board.add({"jobFamilyGroup": ["A"], "timeType": ["FT"]}, 30,
              [_FacetBoard.posting(300 + i) for i in range(30)], [])
    board.add({"jobFamilyGroup": ["A"], "timeType": ["PT"]}, 20,
              [_FacetBoard.posting(400 + i) for i in range(20)], [])

    resolved, collected, warnings = _run_subdivide(board)

    assert resolved is False
    assert len(collected) == 70
    assert WorkdayAdapter.COVERAGE_INCOMPLETE_WARNING in warnings


def test_workday_capability_discovers_classic_dimensions() -> None:
    """1. Classic jobFamilyGroup/workerSubType payload → discovered, usable,
    PARTITION_CANDIDATE vs OVERLAPPING classified, proof off."""
    facets = [
        {"facetParameter": "jobFamilyGroup", "descriptor": "Area",
         "values": [{"id": "A", "count": 30}, {"id": "B", "count": 14}]},
        {"facetParameter": "workerSubType", "descriptor": "Type",
         "values": [{"id": "R", "count": 40}, {"id": "T", "count": 20}]},
    ]
    caps = WorkdayAdapter._discover_capabilities(facets, 44)
    by_param = {cap.parameter: cap for cap in caps}
    assert set(by_param) == {"jobFamilyGroup", "workerSubType"}
    assert by_param["jobFamilyGroup"].usable_for_expansion is True
    assert by_param["jobFamilyGroup"].coverage_class == "PARTITION_CANDIDATE"
    assert by_param["workerSubType"].coverage_class == "OVERLAPPING"
    assert all(cap.proof_eligible is False for cap in caps)
    chosen = WorkdayAdapter._choose_expansion_dimension(caps, {})
    assert chosen is not None and chosen.parameter == "jobFamilyGroup"


def test_workday_capability_discovers_airbus_like_payload() -> None:
    """2. Airbus-like payload (FullPartTime/jobFamily/hiringCompany/nested
    group, no timeType/locations) → real dimensions discovered; nested
    group exposed but unusable; preference still starts at jobFamilyGroup."""
    facets = [
        {"facetParameter": "jobFamilyGroup", "descriptor": "Area",
         "values": [{"id": "A", "count": 636}, {"id": "B", "count": 385}]},
        {"facetParameter": "FullPartTime", "descriptor": "Schedule",
         "values": [{"id": "F", "count": 2696}, {"id": "P", "count": 60}]},
        {"facetParameter": "jobFamily", "descriptor": "Family",
         "values": [{"id": "X", "count": 100}]},
        {"facetParameter": "locationMainGroup", "descriptor": "Location",
         "values": [{"facetParameter": "locationCountry", "descriptor": "Country",
                     "values": []}]},
    ]
    caps = WorkdayAdapter._discover_capabilities(facets, 2000)
    by_param = {cap.parameter: cap for cap in caps}
    assert set(by_param) == {"jobFamilyGroup", "FullPartTime", "jobFamily",
                             "locationMainGroup"}
    nested = by_param["locationMainGroup"]
    assert nested.coverage_class == "NESTED"
    assert nested.filterable is False
    assert nested.usable_for_expansion is False
    assert nested.nested_subgroups == ("locationCountry",)
    assert by_param["jobFamily"].usable_for_expansion is False  # 1 value
    chosen = WorkdayAdapter._choose_expansion_dimension(caps, {})
    assert chosen is not None and chosen.parameter == "jobFamilyGroup"
    # jobFamilyGroup applied → falls back to FullPartTime (preference
    # order), not to payload order.
    fallback = WorkdayAdapter._choose_expansion_dimension(
        caps, {"jobFamilyGroup": ["A"]})
    assert fallback is not None and fallback.parameter == "FullPartTime"


def test_workday_fallback_dimension_used_when_preferred_absent(
    fixtures: Path,
) -> None:
    """3. No preferred dimension usable → payload-discovered fallback
    (jobFamily) partitions for discovery; jobs kept, FALSE."""
    board = _FacetBoard(fixtures)
    board.add({}, 2000, [_FacetBoard.posting(900 + i) for i in range(20)],
              [_FacetBoard.facet("jobFamily", [("X", 30), ("Y", 20)])])
    board.add({"jobFamily": ["X"]}, 30,
              [_FacetBoard.posting(100 + i) for i in range(30)], [])
    board.add({"jobFamily": ["Y"]}, 20,
              [_FacetBoard.posting(200 + i) for i in range(20)], [])

    result = _run_facet_board(board, max_pages=100, max_jobs=5000)

    assert len(result.jobs) == 50
    assert result.is_complete_snapshot is False
    applied = [body["appliedFacets"] for body in board.bodies if body["offset"] == 0]
    assert {"jobFamily": ["X"]} in applied
    assert {"jobFamily": ["Y"]} in applied


def test_workday_partial_and_unknown_stay_usable_without_proof() -> None:
    """4+5. PARTIAL_COVERAGE and UNKNOWN facets: usable_for_expansion TRUE
    (discovery), proof_eligible FALSE (no proof)."""
    partial = WorkdayAdapter._discover_capabilities(
        [{"facetParameter": "Reload_Classification", "descriptor": "Grade",
          "values": [{"id": "G", "count": 100}, {"id": "H", "count": 50}]}],
        2000,
    )[0]
    assert partial.coverage_class == "PARTIAL_COVERAGE"
    assert partial.usable_for_expansion is True
    assert partial.proof_eligible is False
    unknown = WorkdayAdapter._discover_capabilities(
        [{"facetParameter": "hiringCompany", "descriptor": "Co",
          "values": [{"id": "A"}, {"id": "B"}]}],
        2000,
    )[0]
    assert unknown.coverage_class == "UNKNOWN"
    assert unknown.usable_for_expansion is True
    assert unknown.proof_eligible is False


def _capability(facet_parameter, values, parent_total):
    caps = WorkdayAdapter._discover_capabilities(
        [{"facetParameter": facet_parameter, "values":
          [{"id": vid, "count": count} if count is not None else {"id": vid}
           for vid, count in values]}],
        parent_total,
    )
    assert len(caps) == 1
    return caps[0]


def test_workday_capped_parent_sum_above_cap_is_unknown() -> None:
    """Capped 2000, advertised sum 2558 (Airbus shape) → UNKNOWN, never
    OVERLAPPING; still usable for expansion, never proof-eligible."""
    cap = _capability("jobFamilyGroup", [("A", 1400), ("B", 1158)], 2000)
    assert cap.coverage_class == "UNKNOWN"
    assert cap.coverage_class != "OVERLAPPING"
    assert cap.usable_for_expansion is True
    assert cap.proof_eligible is False


def test_workday_capped_parent_sum_equal_cap_is_unknown() -> None:
    """Capped 2000, advertised sum exactly 2000 → UNKNOWN, never
    PARTITION_CANDIDATE (disjoint 1400+600 proves nothing under a cap)."""
    cap = _capability("jobFamilyGroup", [("A", 1400), ("B", 600)], 2000)
    assert cap.coverage_class == "UNKNOWN"
    assert cap.coverage_class != "PARTITION_CANDIDATE"
    assert cap.usable_for_expansion is True
    assert cap.proof_eligible is False


def test_workday_capped_parent_short_sum_is_partial() -> None:
    """Capped 2000, advertised sum 1900 → PARTIAL_COVERAGE (safe refutation);
    expansion stays usable, proof stays off."""
    cap = _capability("jobFamilyGroup", [("A", 1500), ("B", 400)], 2000)
    assert cap.coverage_class == "PARTIAL_COVERAGE"
    assert cap.usable_for_expansion is True
    assert cap.proof_eligible is False


def test_workday_capped_parent_missing_counts_is_unknown() -> None:
    """Capped 2000 with absent counts → UNKNOWN (never treated as zero)."""
    cap = _capability("jobFamilyGroup", [("A", None), ("B", None)], 2000)
    assert cap.coverage_class == "UNKNOWN"
    assert cap.usable_for_expansion is True
    assert cap.proof_eligible is False


def test_workday_uncapped_equal_sum_stays_candidate_only() -> None:
    """Uncapped parent with equal sums keeps PARTITION_CANDIDATE as a
    suggestion only — confidence not upgraded, proof still off."""
    cap = _capability("workerSubType", [("R", 140), ("T", 5)], 145)
    assert cap.coverage_class == "PARTITION_CANDIDATE"
    assert cap.usable_for_expansion is True
    assert cap.proof_eligible is False


def test_workday_failing_branch_keeps_jobs_but_not_complete(fixtures: Path) -> None:
    """One branch errors → collected jobs remain → complete FALSE."""
    board = _FacetBoard(fixtures)
    board.add({}, 2000, [_FacetBoard.posting(900 + i) for i in range(20)],
              [_FacetBoard.facet("jobFamilyGroup", [("A", 20), ("B", 20)])])
    board.add({"jobFamilyGroup": ["A"]}, 20,
              [_FacetBoard.posting(i) for i in range(20)], [])
    board.add({"jobFamilyGroup": ["B"]}, 20, [], [])
    board.fail_routes.add(_FacetBoard.key({"jobFamilyGroup": ["B"]}))

    result = _run_facet_board(board, max_pages=100, max_jobs=5000)

    assert len(result.jobs) == 20
    assert result.is_complete_snapshot is False
    assert WorkdayAdapter.BRANCH_FAILED_WARNING in result.warnings
    assert WorkdayAdapter.CAPPED_TOTAL_WARNING in result.warnings


def test_workday_branch_page_budget_keeps_partial_jobs(fixtures: Path) -> None:
    """Branch hits the page budget → partial jobs kept → complete FALSE."""
    board = _FacetBoard(fixtures)
    board.add({}, 2000, [_FacetBoard.posting(900 + i) for i in range(20)],
              [_FacetBoard.facet("jobFamilyGroup", [("A", 40), ("B", 20)])])
    board.add({"jobFamilyGroup": ["A"]}, 40,
              [_FacetBoard.posting(i) for i in range(40)], [])
    board.add({"jobFamilyGroup": ["B"]}, 20,
              [_FacetBoard.posting(200 + i) for i in range(20)], [])

    result = _run_facet_board(board, max_pages=2, max_jobs=5000)

    assert len(result.jobs) == 20
    assert result.is_complete_snapshot is False
    assert WorkdayAdapter.CAPPED_TOTAL_WARNING in result.warnings


_CHALLENGE_HTML = (
    b"<html><head><title>just a moment...</title></head>"
    b"<body>cf-chl-blocked</body></html>"
)


def _three_branch_board(fixtures: Path) -> _FacetBoard:
    """Capped root with three clean jobFamilyGroup branches (A/B/C)."""
    board = _FacetBoard(fixtures)
    board.add({}, 2000, [_FacetBoard.posting(900 + i) for i in range(20)],
              [_FacetBoard.facet("jobFamilyGroup",
                                 [("A", 20), ("B", 20), ("C", 20)])])
    board.add({"jobFamilyGroup": ["A"]}, 20,
              [_FacetBoard.posting(i) for i in range(20)], [])
    board.add({"jobFamilyGroup": ["B"]}, 20,
              [_FacetBoard.posting(100 + i) for i in range(20)], [])
    board.add({"jobFamilyGroup": ["C"]}, 20,
              [_FacetBoard.posting(200 + i) for i in range(20)], [])
    return board


def _applied_at_offset_zero(board: _FacetBoard) -> list:
    return [body["appliedFacets"] for body in board.bodies if body["offset"] == 0]


def test_workday_challenge_aborts_sibling_branches(fixtures: Path) -> None:
    """TEST A: challenge on child B propagates; sibling C never requested."""
    board = _three_branch_board(fixtures)
    board.raw_overrides[(_FacetBoard.key({"jobFamilyGroup": ["B"]}), 0)] = (
        200, _CHALLENGE_HTML,
    )
    with pytest.raises(AccessChallengeError):
        _run_facet_board(board, max_pages=100, max_jobs=5000)
    applied = _applied_at_offset_zero(board)
    assert {"jobFamilyGroup": ["A"]} in applied
    assert {"jobFamilyGroup": ["C"]} not in applied


def test_workday_circuit_open_aborts_sibling_branches(fixtures: Path) -> None:
    """TEST B: HTTP 429 on child B propagates; sibling C never requested."""
    board = _three_branch_board(fixtures)
    board.raw_overrides[(_FacetBoard.key({"jobFamilyGroup": ["B"]}), 0)] = (
        429, {"error": "slow down"},
    )
    with pytest.raises(HostCircuitOpenError):
        _run_facet_board(board, max_pages=100, max_jobs=5000)
    applied = _applied_at_offset_zero(board)
    assert {"jobFamilyGroup": ["A"]} in applied
    assert {"jobFamilyGroup": ["C"]} not in applied


def test_workday_mid_pagination_abort_stops_everything(fixtures: Path) -> None:
    """TEST C: 429 on page 2 of child A propagates; no further page and no
    sibling B traversal."""
    board = _FacetBoard(fixtures)
    board.add({}, 2000, [_FacetBoard.posting(900 + i) for i in range(20)],
              [_FacetBoard.facet("jobFamilyGroup", [("A", 40), ("B", 20)])])
    board.add({"jobFamilyGroup": ["A"]}, 40,
              [_FacetBoard.posting(i) for i in range(40)], [])
    board.add({"jobFamilyGroup": ["B"]}, 20,
              [_FacetBoard.posting(200 + i) for i in range(20)], [])
    board.raw_overrides[(_FacetBoard.key({"jobFamilyGroup": ["A"]}), 20)] = (
        429, {"error": "slow down"},
    )
    with pytest.raises(HostCircuitOpenError):
        _run_facet_board(board, max_pages=100, max_jobs=5000)
    applied = _applied_at_offset_zero(board)
    assert {"jobFamilyGroup": ["B"]} not in applied


def test_workday_wire_budget_abort_propagates_in_subdivision(
    fixtures: Path,
) -> None:
    """Wire-budget exhaustion inside subdivision propagates (hard abort),
    it is not downgraded to branch failure."""
    board = _FacetBoard(fixtures)
    board.add({}, 2000, [_FacetBoard.posting(900 + i) for i in range(20)],
              [_FacetBoard.facet("jobFamilyGroup", [("A", 40), ("B", 20)])])
    board.add({"jobFamilyGroup": ["A"]}, 40,
              [_FacetBoard.posting(i) for i in range(40)], [])
    board.add({"jobFamilyGroup": ["B"]}, 20,
              [_FacetBoard.posting(200 + i) for i in range(20)], [])
    with pytest.raises(RequestBudgetExceededError):
        _run_facet_board(board, max_pages=100, max_jobs=5000, host_budget=3)


def test_phenom_adapter_parses_embedded_search_data_and_next_link(fixtures: Path) -> None:
    adapter = PhenomAdapter()
    target = _target(
        "https://careers.example.test/us/en/search-results",
        "Phenom frontend",
    )
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        fixture = (
            "phenom_search_page_2.html"
            if request.url.params.get("from") == "1"
            else "phenom_search_page_1.html"
        )
        return httpx.Response(
            200,
            text=(fixtures / fixture).read_text(encoding="utf-8"),
            headers={"Content-Type": "text/html"},
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
            return await adapter.scan(target, PortalScanContext(fetcher))

    result = asyncio.run(run())
    assert result.is_complete_snapshot is True
    assert [job.source_job_id for job in result.jobs] == ["EXAMPLE1001", "EXAMPLE1002"]
    assert result.jobs[0].country == "Italy"
    assert result.jobs[0].description == "Support security monitoring"
    assert result.jobs[1].employment_type == "Internship"
    assert len(requested) == 2


def test_phenom_routing_requires_family_evidence() -> None:
    target = _target(
        "https://careers.example.test/us/en/search-results",
        "Phenom-style branded portal / backend unverified",
    )
    unrelated = _target("https://careers.example.test/jobs", "Custom branded portal")

    assert PhenomAdapter().supports(target) is True
    assert PhenomAdapter().supports(unrelated) is False


def test_phenom_parses_current_server_rendered_first_page() -> None:
    adapter = PhenomAdapter()
    target = _target(
        "https://careers.example.test/search-jobs",
        "Phenom frontend",
    )
    html = """
    <section id="search-results" data-total-job-results="2">
      <section id="search-results-list"><ul><li>
        <a href="/job/rome/security-intern/1/123" data-job-id="123">
          <h2>Security Intern</h2><span class="job-location">Rome, Italy</span>
        </a>
      </li></ul></section>
    </section>
    """

    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(
            200,
            text=html,
            headers={"Content-Type": "text/html"},
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
            return await adapter.scan(target, PortalScanContext(fetcher))

    result = asyncio.run(run())

    assert len(requested) == 1
    assert [job.source_job_id for job in result.jobs] == ["123"]
    assert result.jobs[0].location == "Rome, Italy"
    assert result.is_complete_snapshot is False
    assert result.warnings == (
        "Phenom server-rendered first page contains 1 of 2 jobs",
    )


def test_phenom_routes_verified_cisco_alias() -> None:
    target = _target(
        "https://jobs.cisco.com/jobs/SearchJobs/",
        "Oracle Taleo / Taleo-style",
    )

    assert PhenomAdapter().supports(target) is True


def test_radancy_adapter_paginates_verified_server_rendered_contract(fixtures: Path) -> None:
    adapter = RadancyAdapter()
    target = _target(
        "https://jobs.boeing.com/search-jobs",
        "Custom / branded portal",
    )
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        fixture = (
            "radancy_search_page_2.html"
            if request.url.params.get("p") == "2"
            else "radancy_search_page_1.html"
        )
        return httpx.Response(
            200,
            text=(fixtures / fixture).read_text(encoding="utf-8"),
            headers={"Content-Type": "text/html"},
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
            return await adapter.scan(target, PortalScanContext(fetcher))

    result = asyncio.run(run())

    assert requested == [
        "https://jobs.boeing.com/search-jobs",
        "https://jobs.boeing.com/search-jobs?p=2",
    ]
    assert result.is_complete_snapshot is True
    assert [job.source_job_id for job in result.jobs] == ["101", "102"]
    assert result.jobs[0].location == "Rome, Italy"
    assert result.jobs[1].employment_type == "Internship"


def test_radancy_adapter_honors_page_budget(fixtures: Path) -> None:
    adapter = RadancyAdapter()
    target = _target("https://jobs.boeing.com/search-jobs", "Custom")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=(fixtures / "radancy_search_page_1.html").read_text(encoding="utf-8"),
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
            return await adapter.scan(
                target,
                PortalScanContext(fetcher, max_pages_per_portal=1),
            )

    result = asyncio.run(run())
    assert result.is_complete_snapshot is False
    assert result.warnings == ("Radancy pagination stopped at safety cap of 1 pages",)


def test_radancy_routing_requires_verified_host() -> None:
    adapter = RadancyAdapter()
    verified = _target("https://careers.blackrock.com/en/search-jobs", "Custom")
    unverified = _target("https://jobs.example.test/search-jobs", "Radancy-style")
    unverified_path = _target("https://jobs.paloaltonetworks.com/en/", "Custom")
    assert adapter.supports(verified) is True
    assert adapter.supports(unverified) is False
    assert adapter.supports(unverified_path) is False


def test_avature_adapter_parses_server_rendered_pages(fixtures: Path) -> None:
    adapter = AvatureAdapter()
    target = _target(
        "https://www.metlifecareers.com/en_US/example/SearchJobs/",
        "Oracle Taleo-style",
    )
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        fixture = (
            "avature_search_page_2.html"
            if request.url.params.get("jobOffset") == "1"
            else "avature_search_page_1.html"
        )
        return httpx.Response(
            200,
            text=(fixtures / fixture).read_text(encoding="utf-8"),
            headers={"Content-Type": "text/html"},
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
            return await adapter.scan(target, PortalScanContext(fetcher))

    result = asyncio.run(run())
    assert result.is_complete_snapshot is True
    assert [job.source_job_id for job in result.jobs] == ["1001", "1002"]
    assert result.jobs[0].location == "Milan, Italy"
    assert result.jobs[0].city == "Milan"
    assert result.jobs[0].country == "Italy"
    assert result.jobs[0].posted_at is not None
    assert len(requested) == 2
    assert result.warnings == ("Avature job card 1 is missing title or source id; skipped",)


def test_avature_routing_is_limited_to_verified_hosts_or_family() -> None:
    stale_label = _target(
        "https://jobs.siemens.com/en_US/externaljobs/SearchJobs/",
        "Oracle Taleo / Taleo-style",
    )
    explicit = _target("https://jobs.example.test/SearchJobs/", "Avature")
    unrelated = _target("https://jobs.example.test/SearchJobs/", "Taleo-style")

    assert AvatureAdapter().supports(stale_label) is True
    assert AvatureAdapter().supports(explicit) is True
    assert AvatureAdapter().supports(unrelated) is False


def test_oracle_recruiting_cloud_follows_branded_link_and_paginates(
    fixtures: Path,
) -> None:
    adapter = OracleRecruitingCloudAdapter()
    adapter.page_size = 1
    target = _target(
        "https://careers.example.test/apply",
        "Oracle Recruiting Cloud",
    )
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if request.url.host == "careers.example.test":
            return httpx.Response(
                200,
                text=(
                    '<a href="https://example.fa.oraclecloud.com/hcmUI/'
                    'CandidateExperience/en/sites/CX_1/jobs">Open jobs</a>'
                ),
                request=request,
            )
        if "/hcmUI/" in request.url.path:
            return httpx.Response(
                200,
                text=(fixtures / "oracle_landing.html").read_text(encoding="utf-8"),
                request=request,
            )
        fixture = (
            "oracle_jobs_page_2.json"
            if "offset=1" in str(request.url)
            else "oracle_jobs_page_1.json"
        )
        return httpx.Response(200, json=_fixture(fixtures, fixture), request=request)

    async def run():
        fetcher = HttpFetcher(
            max_retries=0,
            per_domain_min_interval_seconds=0,
            jitter_seconds=0,
            resolve_dns=False,
            transport=httpx.MockTransport(handler),
        )
        async with fetcher:
            return await adapter.scan(target, PortalScanContext(fetcher))

    result = asyncio.run(run())
    assert result.is_complete_snapshot is True
    assert [job.source_job_id for job in result.jobs] == ["1001", "1002"]
    assert result.jobs[0].apply_url == (
        "https://example.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/1001"
    )
    assert result.jobs[1].country == "DE"
    assert len(requested) == 4
    assert "finder=findReqs;siteNumber=CX_1,limit=1,offset=0" in requested[2]


def test_oracle_recruiting_cloud_routing_is_exact() -> None:
    oracle = _target("https://careers.example.test/apply", "Oracle Recruiting Cloud")
    branded = _target(
        "https://www.oracle.com/careers/",
        "Oracle-branded / backend not asserted",
    )

    assert OracleRecruitingCloudAdapter().supports(oracle) is True
    assert OracleRecruitingCloudAdapter().supports(branded) is False


def test_adapter_schema_drift_fails_locally() -> None:
    adapter = GreenhouseAdapter()
    target = _target("https://job-boards.greenhouse.io/example", "Greenhouse")
    with pytest.raises(AdapterSchemaError, match="Greenhouse jobs"):
        _scan(adapter, target, {"unexpected": []})


def test_structured_registry_does_not_invent_recruitee_support() -> None:
    registry = structured_adapter_registry()
    target = _target("https://example.recruitee.com/", "Recruitee")
    assert registry.select(target) is None
