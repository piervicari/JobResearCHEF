"""Lever public Postings API adapter."""

from __future__ import annotations

from urllib.parse import quote, urlsplit

from research_agent.pipeline.http import FetchRequest
from research_agent.sources.ats.common import (
    AdapterSchemaError,
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


class LeverAdapter:
    name = "lever"
    page_size = 100
    max_pages = 100

    def supports(self, target: PortalTarget) -> bool:
        return target.host.lower() in {"jobs.lever.co", "jobs.eu.lever.co"} and any(
            family == "Lever" for family in target.ats_families
        )

    @staticmethod
    def site_and_api_host(target: PortalTarget) -> tuple[str, str]:
        parsed = urlsplit(target.jobs_search_url)
        path_parts = [part for part in parsed.path.split("/") if part]
        if not path_parts:
            raise AdapterSchemaError(f"Cannot derive Lever site from {target.jobs_search_url}")
        api_host = "api.eu.lever.co" if parsed.hostname == "jobs.eu.lever.co" else "api.lever.co"
        return path_parts[0], api_host

    async def scan(
        self, target: PortalTarget, context: PortalScanContext
    ) -> AdapterScanResult:
        site, api_host = self.site_and_api_host(target)
        parsed: list[RawJob] = []
        warnings: list[str] = []
        complete_snapshot = True
        page_limit = context.page_limit(self.max_pages)
        for page_index in range(page_limit):
            skip = page_index * self.page_size
            api_url = (
                f"https://{api_host}/v0/postings/{quote(site, safe='')}"
                f"?mode=json&skip={skip}&limit={self.page_size}"
            )
            response = await context.fetch(
                FetchRequest(api_url, headers={"Accept": "application/json"})
            )
            require_success(response)
            jobs = require_list(response.json(), context="Lever postings")
            for index, value in enumerate(jobs):
                job = require_mapping(value, context=f"Lever postings[{index}]")
                parsed.append(self._parse_job(job, index=index))
            natural_end = len(jobs) < self.page_size
            if len(parsed) > context.max_jobs_per_portal or (
                len(parsed) == context.max_jobs_per_portal and not natural_end
            ):
                parsed = parsed[: context.max_jobs_per_portal]
                warnings.append(
                    f"Lever pagination stopped at job cap of {context.max_jobs_per_portal} records"
                )
                complete_snapshot = False
                break
            if natural_end:
                break
        else:
            warnings.append(
                f"Lever pagination stopped at safety cap of {page_limit} pages"
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
        job_id = string_value(job.get("id"))
        title = string_value(job.get("text"))
        hosted_url = string_value(job.get("hostedUrl"))
        apply_url = string_value(job.get("applyUrl")) or hosted_url
        if not job_id or not title or not hosted_url:
            raise AdapterSchemaError(
                f"Lever postings[{index}] is missing id, text or hostedUrl"
            )
        categories = job.get("categories") or {}
        if not isinstance(categories, dict):
            categories = {}
        all_locations = categories.get("allLocations")
        if isinstance(all_locations, list):
            location = " | ".join(
                item.strip() for item in all_locations if isinstance(item, str) and item.strip()
            )
        else:
            location = string_value(categories.get("location"))
        return RawJob(
            source=self.name,
            source_job_id=job_id,
            source_url=hosted_url,
            apply_url=apply_url,
            title=title,
            location=location,
            country=string_value(job.get("country")) or None,
            description=string_value(job.get("descriptionPlain")),
            employment_type=string_value(categories.get("commitment")) or None,
            workplace_type=string_value(job.get("workplaceType")) or None,
            ats_job_id=job_id,
            raw_payload=job,
        )
