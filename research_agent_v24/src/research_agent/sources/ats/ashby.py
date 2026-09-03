"""Ashby public Job Postings API adapter."""

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


class AshbyAdapter:
    name = "ashby"
    bulk_catalog = True

    def supports(self, target: PortalTarget) -> bool:
        return target.host.lower() == "jobs.ashbyhq.com" and any(
            family == "Ashby" for family in target.ats_families
        )

    @staticmethod
    def board_name(target: PortalTarget) -> str:
        parts = [part for part in urlsplit(target.jobs_search_url).path.split("/") if part]
        if not parts:
            raise AdapterSchemaError(f"Cannot derive Ashby board from {target.jobs_search_url}")
        return parts[0]

    async def scan(
        self, target: PortalTarget, context: PortalScanContext
    ) -> AdapterScanResult:
        board = quote(self.board_name(target), safe="")
        api_url = f"https://api.ashbyhq.com/posting-api/job-board/{board}"
        response = await context.fetch(
            FetchRequest(api_url, headers={"Accept": "application/json"})
        )
        require_success(response)
        payload = require_mapping(response.json(), context="Ashby response")
        jobs = require_list(payload.get("jobs"), context="Ashby jobs")
        parsed: list[RawJob] = []
        for index, value in enumerate(jobs):
            job = require_mapping(value, context=f"Ashby jobs[{index}]")
            if job.get("isListed") is False:
                continue
            title = string_value(job.get("title"))
            job_url = string_value(job.get("jobUrl"))
            apply_url = string_value(job.get("applyUrl")) or job_url
            if not title or not job_url:
                raise AdapterSchemaError(
                    f"Ashby jobs[{index}] is missing title or jobUrl"
                )
            address = job.get("address") or {}
            postal = address.get("postalAddress") if isinstance(address, dict) else {}
            if not isinstance(postal, dict):
                postal = {}
            parsed.append(
                RawJob(
                    source=self.name,
                    source_job_id=job_url,
                    source_url=job_url,
                    apply_url=apply_url,
                    title=title,
                    location=string_value(job.get("location")),
                    country=string_value(postal.get("addressCountry")) or None,
                    city=string_value(postal.get("addressLocality")) or None,
                    description=string_value(job.get("descriptionPlain")),
                    posted_at=parse_datetime(job.get("publishedAt")),
                    employment_type=string_value(job.get("employmentType")) or None,
                    workplace_type=string_value(job.get("workplaceType")) or None,
                    ats_job_id=job_url,
                    raw_payload=job,
                )
            )
        warnings: tuple[str, ...] = ()
        complete = True
        if len(parsed) > context.max_jobs_per_portal:
            parsed = parsed[: context.max_jobs_per_portal]
            complete = False
            warnings = (
                f"Ashby response stopped at job cap of {context.max_jobs_per_portal} records",
            )
        elif not parsed:
            warnings = ("upstream reports zero active jobs",)
        return AdapterScanResult(
            jobs=tuple(parsed), warnings=warnings, is_complete_snapshot=complete
        )
