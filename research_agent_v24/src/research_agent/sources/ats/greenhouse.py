"""Greenhouse public Job Board API adapter."""

from __future__ import annotations

from urllib.parse import quote, urlsplit

from research_agent.pipeline.http import FetchRequest
from research_agent.sources.ats.common import (
    AdapterSchemaError,
    require_list,
    parse_datetime,
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


class GreenhouseAdapter:
    name = "greenhouse"
    bulk_catalog = True
    _DIRECT_HOSTS = {"boards.greenhouse.io", "job-boards.greenhouse.io"}

    def supports(self, target: PortalTarget) -> bool:
        return target.host.lower() in self._DIRECT_HOSTS and any(
            family == "Greenhouse" for family in target.ats_families
        )

    @staticmethod
    def board_token(target: PortalTarget) -> str:
        path_parts = [part for part in urlsplit(target.jobs_search_url).path.split("/") if part]
        if not path_parts:
            raise AdapterSchemaError(
                f"Cannot derive Greenhouse board token from {target.jobs_search_url}"
            )
        return path_parts[0]

    async def scan(
        self, target: PortalTarget, context: PortalScanContext
    ) -> AdapterScanResult:
        token = quote(self.board_token(target), safe="")
        api_url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
        response = await context.fetch(
            FetchRequest(api_url, headers={"Accept": "application/json"})
        )
        require_success(response)
        payload = require_mapping(response.json(), context="Greenhouse response")
        jobs = require_list(payload.get("jobs"), context="Greenhouse jobs")
        parsed: list[RawJob] = []
        for index, value in enumerate(jobs):
            job = require_mapping(value, context=f"Greenhouse jobs[{index}]")
            job_id = job.get("id")
            title = string_value(job.get("title"))
            absolute_url = string_value(job.get("absolute_url"))
            if job_id is None or not title or not absolute_url:
                raise AdapterSchemaError(
                    f"Greenhouse jobs[{index}] is missing id, title or absolute_url"
                )
            location_value = job.get("location") or {}
            location = (
                string_value(location_value.get("name"))
                if isinstance(location_value, dict)
                else ""
            )
            parsed.append(
                RawJob(
                    source=self.name,
                    source_job_id=str(job_id),
                    source_url=absolute_url,
                    apply_url=absolute_url,
                    title=title,
                    location=location,
                    description=string_value(job.get("content")),
                    posted_at=(
                        parse_datetime(job.get("first_published"))
                        or parse_datetime(job.get("updated_at"))
                    ),
                    ats_job_id=str(job_id),
                    requisition_id=(
                        str(job["requisition_id"])
                        if job.get("requisition_id") is not None
                        else None
                    ),
                    raw_payload=job,
                )
            )
        warnings: tuple[str, ...] = ()
        complete = True
        if len(parsed) > context.max_jobs_per_portal:
            parsed = parsed[: context.max_jobs_per_portal]
            complete = False
            warnings = (
                f"Greenhouse response stopped at job cap of {context.max_jobs_per_portal} records",
            )
        elif not parsed:
            warnings = ("upstream reports zero active jobs",)
        return AdapterScanResult(
            jobs=tuple(parsed), warnings=warnings, is_complete_snapshot=complete
        )
