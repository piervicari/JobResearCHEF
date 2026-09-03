"""Phenom Career Connect server-rendered search data adapter."""

from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlsplit

from selectolax.parser import HTMLParser, Node

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


class PhenomAdapter:
    name = "phenom"
    max_pages = 100
    _DDO = re.compile(
        r"phApp\.ddo\s*=\s*(\{.*?\});\s*phApp\.experimentData",
        re.DOTALL,
    )
    _BASE_URL = re.compile(r'"baseUrl"\s*:\s*"([^"]+)"')

    def supports(self, target: PortalTarget) -> bool:
        return target.host.casefold() == "jobs.cisco.com" or any(
            "phenom" in family.casefold() for family in target.ats_families
        )

    async def scan(self, target: PortalTarget, context: PortalScanContext) -> AdapterScanResult:
        first = await context.fetch(
            FetchRequest(target.jobs_search_url, headers={"Accept": "text/html"})
        )
        require_success(first)
        response = first
        try:
            ddo = self._extract_ddo(first.text)
        except AdapterSchemaError:
            return self._server_rendered_result(
                first.text,
                base_url=first.final_url,
                max_jobs=context.max_jobs_per_portal,
            )
        if "eagerLoadRefineSearch" not in ddo:
            base_url = self._extract_base_url(first.text)
            search_url = urljoin(base_url, "search-results")
            if search_url != first.final_url:
                response = await context.fetch(
                    FetchRequest(search_url, headers={"Accept": "text/html"})
                )
                require_success(response)
                ddo = self._extract_ddo(response.text)

        next_url: str | None = response.final_url
        first_page = (response, ddo)
        seen_pages: set[str] = set()
        seen_jobs: set[str] = set()
        parsed_jobs: list[RawJob] = []
        warnings: list[str] = []
        expected_total: int | None = None
        complete = True

        page_limit = context.page_limit(self.max_pages)
        for page_index in range(page_limit):
            if next_url is None:
                break
            if next_url in seen_pages:
                raise AdapterSchemaError(f"Phenom pagination loop at {next_url}")
            seen_pages.add(next_url)
            if page_index == 0:
                page_response, page_ddo = first_page
            else:
                page_response = await context.fetch(
                    FetchRequest(next_url, headers={"Accept": "text/html"})
                )
                require_success(page_response)
                page_ddo = self._extract_ddo(page_response.text)
            jobs, total = self._page_jobs(page_ddo)
            if expected_total is None:
                expected_total = total
            elif total != expected_total:
                warnings.append(
                    f"Phenom total changed during pagination: {expected_total} -> {total}"
                )
            for index, job in enumerate(jobs):
                parsed = self._parse_job(job, index=index)
                if parsed.source_job_id in seen_jobs:
                    continue
                seen_jobs.add(parsed.source_job_id)
                parsed_jobs.append(parsed)
            natural_end = len(parsed_jobs) >= expected_total
            if len(parsed_jobs) > context.max_jobs_per_portal or (
                len(parsed_jobs) == context.max_jobs_per_portal and not natural_end
            ):
                parsed_jobs = parsed_jobs[: context.max_jobs_per_portal]
                complete = False
                warnings.append(
                    f"Phenom pagination stopped at job cap of {context.max_jobs_per_portal} records"
                )
                next_url = None
                break
            if natural_end:
                next_url = None
                break
            next_url = self._next_page_url(page_response.text, page_response.final_url)
            if next_url is None:
                complete = False
                warnings.append(
                    f"Phenom pagination ended at {len(parsed_jobs)} of {expected_total} jobs"
                )
                break
        else:
            complete = False
            warnings.append(
                f"Phenom pagination stopped at safety cap of {page_limit} pages"
            )

        if expected_total == 0:
            warnings.append("upstream reports zero active jobs")

        return AdapterScanResult(
            jobs=tuple(parsed_jobs),
            warnings=tuple(warnings),
            is_complete_snapshot=complete,
        )

    def _server_rendered_result(
        self, html: str, *, base_url: str, max_jobs: int
    ) -> AdapterScanResult:
        """Parse the current Phenom server-rendered list when legacy DDO is absent."""

        document = HTMLParser(html)
        search = document.css_first("#search-results")
        if search is None:
            raise AdapterSchemaError(
                "Phenom page has neither phApp.ddo nor a server-rendered search result list"
            )
        raw_total = search.attributes.get("data-total-job-results", "").strip()
        try:
            total = int(raw_total)
        except ValueError as exc:
            raise AdapterSchemaError(
                "Phenom server-rendered search is missing data-total-job-results"
            ) from exc

        jobs: list[RawJob] = []
        warnings: list[str] = []
        for index, anchor in enumerate(
            document.css('#search-results-list a[href][data-job-id]')
        ):
            title_node = anchor.css_first("h3") or anchor.css_first("h2")
            title = self._node_text(title_node)
            source_job_id = anchor.attributes.get("data-job-id", "").strip()
            href = anchor.attributes.get("href", "").strip()
            if not title or not source_job_id or not href:
                warnings.append(
                    f"Phenom server-rendered job card {index} is incomplete; skipped"
                )
                continue
            locations = [
                self._node_text(node)
                for node in anchor.css(".job-location")
                if self._node_text(node)
            ]
            job_url = urljoin(base_url, href)
            jobs.append(
                RawJob(
                    source=self.name,
                    source_job_id=source_job_id,
                    source_url=job_url,
                    apply_url=job_url,
                    title=title,
                    location=" | ".join(locations),
                    ats_job_id=source_job_id,
                    requisition_id=source_job_id,
                    raw_payload={
                        "href": href,
                        "server_rendered": True,
                    },
                )
            )

        if total > 0 and not jobs:
            raise AdapterSchemaError(
                "Phenom server-rendered search reports jobs but contains no parseable cards"
            )
        complete = len(jobs) >= total
        if len(jobs) > max_jobs:
            jobs = jobs[:max_jobs]
            complete = False
            warnings.append(
                f"Phenom server-rendered result stopped at job cap of {max_jobs} records"
            )
        elif not complete:
            warnings.append(
                f"Phenom server-rendered first page contains {len(jobs)} of {total} jobs"
            )
        elif total == 0:
            warnings.append("upstream reports zero active jobs")
        return AdapterScanResult(
            jobs=tuple(jobs),
            warnings=tuple(warnings),
            is_complete_snapshot=complete,
        )

    @staticmethod
    def _node_text(node: Node | None) -> str:
        return " ".join(node.text(separator=" ").split()) if node is not None else ""

    @classmethod
    def _extract_ddo(cls, html: str) -> dict[str, object]:
        matched = cls._DDO.search(html)
        if matched is None:
            raise AdapterSchemaError("Phenom page is missing server-rendered phApp.ddo")
        try:
            return require_mapping(json.loads(matched.group(1)), context="Phenom phApp.ddo")
        except json.JSONDecodeError as exc:
            raise AdapterSchemaError(f"Invalid Phenom phApp.ddo JSON: {exc}") from exc

    @classmethod
    def _extract_base_url(cls, html: str) -> str:
        matched = cls._BASE_URL.search(html)
        if matched is None:
            raise AdapterSchemaError("Phenom page is missing baseUrl")
        return matched.group(1).replace("\\/", "/")

    @staticmethod
    def _page_jobs(ddo: dict[str, object]) -> tuple[list[dict[str, object]], int]:
        search = require_mapping(
            ddo.get("eagerLoadRefineSearch"), context="Phenom eagerLoadRefineSearch"
        )
        total = search.get("totalHits")
        if not isinstance(total, int) or total < 0:
            raise AdapterSchemaError("Phenom search is missing non-negative totalHits")
        data = require_mapping(search.get("data"), context="Phenom search data")
        values = require_list(data.get("jobs"), context="Phenom jobs")
        return [
            require_mapping(value, context=f"Phenom jobs[{index}]")
            for index, value in enumerate(values)
        ], total

    @staticmethod
    def _next_page_url(html: str, base_url: str) -> str | None:
        document = HTMLParser(html)
        node = document.css_first('link[rel="next"]')
        if node is None:
            return None
        href = node.attributes.get("href", "").strip()
        if not href:
            return None
        result = urljoin(base_url, href)
        if urlsplit(result).hostname != urlsplit(base_url).hostname:
            raise AdapterSchemaError(f"Phenom next link changes host: {result}")
        return result

    def _parse_job(self, job: dict[str, object], *, index: int) -> RawJob:
        source_job_id = string_value(job.get("jobSeqNo")) or string_value(job.get("jobId"))
        title = string_value(job.get("title"))
        apply_url = string_value(job.get("applyUrl"))
        if not source_job_id or not title or not apply_url:
            raise AdapterSchemaError(
                f"Phenom jobs[{index}] is missing jobSeqNo/jobId, title or applyUrl"
            )
        source_url = apply_url.removesuffix("/apply")
        location = string_value(job.get("cityStateCountry")) or string_value(job.get("location"))
        country = string_value(job.get("country")) or None
        return RawJob(
            source=self.name,
            source_job_id=source_job_id,
            source_url=source_url,
            apply_url=apply_url,
            title=title,
            location=location,
            country=country,
            description=string_value(job.get("descriptionTeaser")),
            posted_at=parse_datetime(job.get("postedDate")),
            employment_type=string_value(job.get("type")) or None,
            workplace_type=("remote" if "remote" in location.casefold() else None),
            ats_job_id=string_value(job.get("jobId")) or source_job_id,
            requisition_id=string_value(job.get("reqId")) or None,
            raw_payload=job,
        )
