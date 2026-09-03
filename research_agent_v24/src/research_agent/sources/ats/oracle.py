"""Oracle Recruiting Cloud public Candidate Experience adapter."""

from __future__ import annotations

from urllib.parse import quote, urljoin, urlsplit, urlunsplit

from selectolax.parser import HTMLParser

from research_agent.pipeline.http import FetchRequest
from research_agent.sources.ats.common import (
    AdapterSchemaError,
    parse_datetime,
    require_list,
    require_mapping,
    require_success,
    string_value,
)
from research_agent.sources.base import (
    AdapterScanResult,
    PortalScanContext,
    PortalTarget,
    RawJob,
)


class OracleRecruitingCloudAdapter:
    name = "oracle_recruiting_cloud"
    page_size = 25
    max_pages = 100

    def supports(self, target: PortalTarget) -> bool:
        return any(
            family.casefold() == "oracle recruiting cloud"
            for family in target.ats_families
        )

    async def scan(
        self, target: PortalTarget, context: PortalScanContext
    ) -> AdapterScanResult:
        landing = await context.fetch(
            FetchRequest(target.jobs_search_url, headers={"Accept": "text/html"})
        )
        require_success(landing)
        oracle_landing = landing
        bootstrap = self._bootstrap(landing.text, landing.final_url)
        if bootstrap is None:
            linked = self._linked_candidate_experience(landing.text, landing.final_url)
            if linked is None:
                raise AdapterSchemaError(
                    "Oracle Recruiting Cloud page has no Candidate Experience bootstrap or link"
                )
            oracle_landing = await context.fetch(
                FetchRequest(linked, headers={"Accept": "text/html"})
            )
            require_success(oracle_landing)
            bootstrap = self._bootstrap(oracle_landing.text, oracle_landing.final_url)
        if bootstrap is None:
            raise AdapterSchemaError(
                "Oracle Candidate Experience bootstrap is missing base metadata"
            )
        api_origin, site_number, candidate_base = bootstrap

        parsed_jobs: list[RawJob] = []
        warnings: list[str] = []
        total: int | None = None
        complete = True
        page_limit = context.page_limit(self.max_pages)
        for page_index in range(page_limit):
            offset = page_index * self.page_size
            finder = (
                f"findReqs;siteNumber={quote(site_number, safe='')},"
                f"limit={self.page_size},offset={offset}"
            )
            api_url = (
                f"{api_origin}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
                "?onlyData=true&expand=requisitionList.secondaryLocations"
                f"&finder={finder}"
            )
            response = await context.fetch(
                FetchRequest(api_url, headers={"Accept": "application/json"})
            )
            require_success(response)
            payload = require_mapping(response.json(), context="Oracle recruiting response")
            items = require_list(payload.get("items"), context="Oracle recruiting items")
            if len(items) != 1:
                raise AdapterSchemaError(
                    f"Oracle recruiting response expected one search item, got {len(items)}"
                )
            search = require_mapping(items[0], context="Oracle recruiting search item")
            raw_total = search.get("TotalJobsCount")
            if not isinstance(raw_total, int) or raw_total < 0:
                raise AdapterSchemaError("Oracle search is missing non-negative TotalJobsCount")
            if total is None:
                total = raw_total
            elif total != raw_total:
                warnings.append(
                    f"Oracle total changed during pagination: {total} -> {raw_total}"
                )
            values = require_list(
                search.get("requisitionList"), context="Oracle requisitionList"
            )
            for index, value in enumerate(values):
                job = require_mapping(value, context=f"Oracle requisitionList[{index}]")
                parsed_jobs.append(
                    self._parse_job(job, candidate_base=candidate_base, index=index)
                )
            natural_end = offset + len(values) >= total or len(values) < self.page_size
            if len(parsed_jobs) > context.max_jobs_per_portal or (
                len(parsed_jobs) == context.max_jobs_per_portal and not natural_end
            ):
                parsed_jobs = parsed_jobs[: context.max_jobs_per_portal]
                complete = False
                warnings.append(
                    "Oracle pagination stopped at job cap of "
                    f"{context.max_jobs_per_portal} records"
                )
                break
            if natural_end:
                break
            if not values:
                raise AdapterSchemaError(
                    f"Oracle returned an empty page before total at offset {offset}"
                )
        else:
            complete = False
            warnings.append(
                f"Oracle pagination stopped at safety cap of {page_limit} pages"
            )

        if total == 0:
            warnings.append("upstream reports zero active jobs")

        return AdapterScanResult(
            jobs=tuple(parsed_jobs),
            warnings=tuple(warnings),
            is_complete_snapshot=complete,
        )

    @staticmethod
    def _bootstrap(html: str, page_url: str) -> tuple[str, str, str] | None:
        document = HTMLParser(html)
        base = document.css_first("base[data-apibaseurl][data-sitenumber]")
        if base is None:
            return None
        raw_api = base.attributes.get("data-apibaseurl", "").strip()
        site = base.attributes.get("data-sitenumber", "").strip()
        base_href = base.attributes.get("href", "").strip()
        if not raw_api or not site or not base_href:
            return None
        parsed_api = urlsplit(raw_api)
        api_origin = urlunsplit((parsed_api.scheme, parsed_api.netloc, "", "", ""))
        candidate_base = urljoin(page_url, base_href).rstrip("/")
        return api_origin, site, candidate_base

    @staticmethod
    def _linked_candidate_experience(html: str, page_url: str) -> str | None:
        document = HTMLParser(html)
        for anchor in document.css("a[href]"):
            absolute = urljoin(page_url, anchor.attributes.get("href", ""))
            path = urlsplit(absolute).path
            if "/hcmUI/CandidateExperience/" in path and "/sites/" in path:
                return absolute
        return None

    def _parse_job(
        self, job: dict[str, object], *, candidate_base: str, index: int
    ) -> RawJob:
        job_id = string_value(job.get("Id"))
        title = string_value(job.get("Title"))
        if not job_id or not title:
            raise AdapterSchemaError(
                f"Oracle requisitionList[{index}] is missing Id or Title"
            )
        job_url = f"{candidate_base}/job/{quote(job_id, safe='')}"
        description = string_value(job.get("ShortDescriptionStr"))
        if not description:
            description = " ".join(
                value
                for value in (
                    string_value(job.get("ExternalResponsibilitiesStr")),
                    string_value(job.get("ExternalQualificationsStr")),
                )
                if value
            )
        return RawJob(
            source=self.name,
            source_job_id=job_id,
            source_url=job_url,
            apply_url=job_url,
            title=title,
            location=string_value(job.get("PrimaryLocation")),
            country=string_value(job.get("PrimaryLocationCountry")) or None,
            description=description,
            posted_at=parse_datetime(job.get("PostedDate")),
            employment_type=(
                string_value(job.get("JobType"))
                or string_value(job.get("WorkerType"))
                or None
            ),
            workplace_type=string_value(job.get("WorkplaceType")) or None,
            ats_job_id=job_id,
            requisition_id=job_id,
            raw_payload=job,
        )
