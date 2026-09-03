import asyncio
import json
from pathlib import Path

import httpx
import pytest

from research_agent.pipeline.http import HttpFetcher
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
from research_agent.sources.base import PortalScanContext, PortalTarget


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

    assert requested == ["https://api.ashbyhq.com/posting-api/job-board/example"]
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
