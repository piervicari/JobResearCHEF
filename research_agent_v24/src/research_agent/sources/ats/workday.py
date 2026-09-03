"""Workday Candidate Experience public jobs endpoint adapter."""

from __future__ import annotations

import re
from urllib.parse import quote, urlsplit, urlunsplit

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


class WorkdayAdapter:
    name = "workday"
    page_size = 20
    max_pages = 100
    _TENANT = re.compile(r"\btenant\s*:\s*['\"]([^'\"]+)['\"]")
    _SITE = re.compile(r"\bsiteId\s*:\s*['\"]([^'\"]+)['\"]")
    _SUPPORTED_FAMILIES = {"workday", "workday recruiting"}

    def supports(self, target: PortalTarget) -> bool:
        host = target.host.casefold()
        direct_host = host.endswith(".myworkdayjobs.com") or host.endswith(
            ".myworkdaysite.com"
        )
        return direct_host and any(
            family.casefold() in self._SUPPORTED_FAMILIES for family in target.ats_families
        )

    async def scan(
        self, target: PortalTarget, context: PortalScanContext
    ) -> AdapterScanResult:
        landing = await context.fetch(
            FetchRequest(target.jobs_search_url, headers={"Accept": "text/html"})
        )
        require_success(landing)
        tenant, site = self._bootstrap_identifiers(landing.text)
        parsed_landing = urlsplit(landing.final_url)
        origin = urlunsplit((parsed_landing.scheme, parsed_landing.netloc, "", "", ""))
        api_url = (
            f"{origin}/wday/cxs/{quote(tenant, safe='')}/{quote(site, safe='')}/jobs"
        )
        site_url = f"{origin}/{quote(site, safe='')}"
        parsed_jobs: list[RawJob] = []
        warnings: list[str] = []
        complete = True
        total: int | None = None

        page_limit = context.page_limit(self.max_pages)
        for page_index in range(page_limit):
            offset = page_index * self.page_size
            response = await context.fetch(
                FetchRequest(
                    api_url,
                    method="POST",
                    allow_cache=False,
                    headers={"Accept": "application/json"},
                    json_body={
                        "appliedFacets": {},
                        "limit": self.page_size,
                        "offset": offset,
                        "searchText": "",
                    },
                )
            )
            require_success(response)
            payload = require_mapping(response.json(), context="Workday jobs response")
            jobs = require_list(payload.get("jobPostings"), context="Workday jobPostings")
            raw_total = payload.get("total")
            if not isinstance(raw_total, int) or raw_total < 0:
                raise AdapterSchemaError("Workday jobs response is missing non-negative total")
            if total is None:
                total = raw_total
            elif total != raw_total:
                warning = f"Workday total changed during pagination: {total} -> {raw_total}"
                if warning not in warnings:
                    warnings.append(warning)
            for index, value in enumerate(jobs):
                job = require_mapping(value, context=f"Workday jobPostings[{index}]")
                try:
                    parsed_jobs.append(self._parse_job(job, site_url=site_url, index=index))
                except AdapterSchemaError as exc:
                    complete = False
                    warnings.append(f"{exc}; skipped")
            natural_end = offset + len(jobs) >= total or len(jobs) < self.page_size
            if len(parsed_jobs) > context.max_jobs_per_portal or (
                len(parsed_jobs) == context.max_jobs_per_portal and not natural_end
            ):
                parsed_jobs = parsed_jobs[: context.max_jobs_per_portal]
                complete = False
                warnings.append(
                    "Workday pagination stopped at job cap of "
                    f"{context.max_jobs_per_portal} records"
                )
                break
            if natural_end:
                break
            if not jobs:
                raise AdapterSchemaError(
                    f"Workday returned an empty page before total at offset {offset}"
                )
        else:
            complete = False
            warnings.append(
                f"Workday pagination stopped at safety cap of {page_limit} pages"
            )

        if total == 0:
            warnings.append("upstream reports zero active jobs")

        return AdapterScanResult(
            jobs=tuple(parsed_jobs),
            warnings=tuple(warnings),
            is_complete_snapshot=complete,
        )

    @classmethod
    def _bootstrap_identifiers(cls, html: str) -> tuple[str, str]:
        tenant_match = cls._TENANT.search(html)
        site_match = cls._SITE.search(html)
        if tenant_match is None or site_match is None:
            raise AdapterSchemaError("Workday bootstrap is missing tenant or siteId")
        return tenant_match.group(1), site_match.group(1)

    def _parse_job(
        self, job: dict[str, object], *, site_url: str, index: int
    ) -> RawJob:
        title = string_value(job.get("title"))
        external_path = string_value(job.get("externalPath"))
        if not title or not external_path:
            raise AdapterSchemaError(
                f"Workday jobPostings[{index}] is missing title or externalPath"
            )
        normalized_path = (
            external_path if external_path.startswith("/") else f"/{external_path}"
        )
        job_url = f"{site_url}{normalized_path}"
        bullets = job.get("bulletFields")
        requisition = ""
        if isinstance(bullets, list):
            requisition = next(
                (value.strip() for value in bullets if isinstance(value, str) and value.strip()),
                "",
            )
        source_job_id = requisition or external_path
        return RawJob(
            source=self.name,
            source_job_id=source_job_id,
            source_url=job_url,
            apply_url=job_url,
            title=title,
            location=string_value(job.get("locationsText")),
            ats_job_id=source_job_id,
            requisition_id=requisition or None,
            raw_payload=job,
        )
