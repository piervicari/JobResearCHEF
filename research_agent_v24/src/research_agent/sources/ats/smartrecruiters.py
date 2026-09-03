"""SmartRecruiters public Posting API adapter."""

from __future__ import annotations

from urllib.parse import quote, urlsplit

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


class SmartRecruitersAdapter:
    name = "smartrecruiters"
    page_size = 100
    max_pages = 100

    def supports(self, target: PortalTarget) -> bool:
        return target.host.lower() == "careers.smartrecruiters.com" and any(
            family == "SmartRecruiters" for family in target.ats_families
        )

    @staticmethod
    def company_identifier(target: PortalTarget) -> str:
        parts = [part for part in urlsplit(target.jobs_search_url).path.split("/") if part]
        if not parts:
            raise AdapterSchemaError(
                f"Cannot derive SmartRecruiters company from {target.jobs_search_url}"
            )
        return parts[0]

    async def scan(
        self, target: PortalTarget, context: PortalScanContext
    ) -> AdapterScanResult:
        company = self.company_identifier(target)
        parsed: list[RawJob] = []
        warnings: list[str] = []
        complete_snapshot = True
        page_limit = context.page_limit(self.max_pages)
        for page_index in range(page_limit):
            offset = page_index * self.page_size
            api_url = (
                "https://api.smartrecruiters.com/v1/companies/"
                f"{quote(company, safe='')}/postings?limit={self.page_size}&offset={offset}"
            )
            response = await context.fetch(
                FetchRequest(api_url, headers={"Accept": "application/json"})
            )
            require_success(response)
            payload = require_mapping(response.json(), context="SmartRecruiters response")
            content = require_list(payload.get("content"), context="SmartRecruiters content")
            for index, value in enumerate(content):
                job = require_mapping(value, context=f"SmartRecruiters content[{index}]")
                parsed.append(self._parse_job(job, index=index))
            total = payload.get("totalFound")
            natural_end = len(content) < self.page_size or (
                isinstance(total, int) and offset + len(content) >= total
            )
            if len(parsed) > context.max_jobs_per_portal or (
                len(parsed) == context.max_jobs_per_portal and not natural_end
            ):
                parsed = parsed[: context.max_jobs_per_portal]
                warnings.append(
                    "SmartRecruiters pagination stopped at job cap of "
                    f"{context.max_jobs_per_portal} records"
                )
                complete_snapshot = False
                break
            if natural_end:
                break
        else:
            warnings.append(
                f"SmartRecruiters pagination stopped at safety cap of {page_limit} pages"
            )
            complete_snapshot = False
        if not parsed and complete_snapshot:
            warnings.append("upstream reports zero active jobs")
        return AdapterScanResult(
            jobs=tuple(parsed),
            warnings=tuple(warnings),
            is_complete_snapshot=complete_snapshot,
        )

    def _parse_job(self, job: dict[str, object], *, index: int) -> RawJob:
        job_id = string_value(job.get("id")) or string_value(job.get("uuid"))
        title = string_value(job.get("name"))
        if not job_id or not title:
            raise AdapterSchemaError(f"SmartRecruiters content[{index}] is missing id or name")
        company_value = job.get("company") or {}
        company_name = (
            string_value(company_value.get("name"))
            if isinstance(company_value, dict)
            else ""
        )
        location_value = job.get("location") or {}
        location_parts: list[str] = []
        workplace_type: str | None = None
        country: str | None = None
        city: str | None = None
        if isinstance(location_value, dict):
            location_parts = [
                string_value(location_value.get(field))
                for field in ("city", "region", "country")
            ]
            if location_value.get("remote") is True:
                workplace_type = "remote"
            country = string_value(location_value.get("country")) or None
            city = string_value(location_value.get("city")) or None
        employment = job.get("typeOfEmployment") or {}
        employment_type = (
            string_value(employment.get("label"))
            if isinstance(employment, dict)
            else ""
        )
        ref = string_value(job.get("ref"))
        return RawJob(
            source=self.name,
            source_job_id=job_id,
            source_url=ref,
            apply_url=ref,
            title=title,
            company=company_name,
            location=", ".join(part for part in location_parts if part),
            country=country,
            city=city,
            posted_at=parse_datetime(job.get("releasedDate")),
            employment_type=employment_type or None,
            workplace_type=workplace_type,
            ats_job_id=job_id,
            raw_payload=job,
        )
