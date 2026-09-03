"""Avature server-rendered career portal adapter."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit

from selectolax.parser import HTMLParser, Node

from research_agent.pipeline.http import FetchRequest
from research_agent.sources.ats.common import (
    AdapterSchemaError,
    parse_datetime,
    require_success,
)
from research_agent.sources.base import (
    AdapterScanResult,
    PortalScanContext,
    PortalTarget,
    RawJob,
)


class AvatureAdapter:
    """Parse Avature's public, server-rendered SearchJobs pages."""

    name = "avature"
    max_pages = 100
    _KNOWN_HOSTS = {"jobs.siemens.com", "www.metlifecareers.com"}
    _TOTAL = re.compile(r"(?P<count>\d+)\s*(?P<plus>\+)?\s+results?", re.I)

    def supports(self, target: PortalTarget) -> bool:
        return target.host.casefold() in self._KNOWN_HOSTS or any(
            family.casefold() == "avature" for family in target.ats_families
        )

    async def scan(self, target: PortalTarget, context: PortalScanContext) -> AdapterScanResult:
        next_url: str | None = target.jobs_search_url
        seen_pages: set[str] = set()
        seen_jobs: set[str] = set()
        jobs: list[RawJob] = []
        warnings: list[str] = []
        expected_total: int | None = None
        exact_total = False
        complete = True

        page_limit = context.page_limit(self.max_pages)
        for _ in range(page_limit):
            if next_url is None:
                break
            if next_url in seen_pages:
                raise AdapterSchemaError(f"Avature pagination loop at {next_url}")
            seen_pages.add(next_url)
            response = await context.fetch(FetchRequest(next_url, headers={"Accept": "text/html"}))
            require_success(response)
            document = HTMLParser(response.text)
            self._require_avature_page(document)
            page_jobs, page_warnings = self._parse_jobs(document, base_url=response.final_url)
            warnings.extend(page_warnings)
            if not page_jobs and not jobs:
                raise AdapterSchemaError("Avature SearchJobs page contains no job cards")
            for job in page_jobs:
                if job.source_job_id not in seen_jobs:
                    seen_jobs.add(job.source_job_id)
                    jobs.append(job)

            if expected_total is None:
                expected_total, exact_total = self._expected_total(document)
            next_url = self._next_url(document, base_url=response.final_url)
            if exact_total and expected_total is not None and len(jobs) >= expected_total:
                next_url = None
            if len(jobs) > context.max_jobs_per_portal or (
                len(jobs) == context.max_jobs_per_portal and next_url is not None
            ):
                jobs = jobs[: context.max_jobs_per_portal]
                complete = False
                warnings.append(
                    "Avature pagination stopped at job cap of "
                    f"{context.max_jobs_per_portal} records"
                )
                break
            if next_url is None:
                if exact_total and expected_total is not None and len(jobs) != expected_total:
                    complete = False
                    warnings.append(
                        f"Avature pagination ended at {len(jobs)} of {expected_total} jobs"
                    )
                break
        else:
            complete = False
            warnings.append(
                f"Avature pagination stopped at safety cap of {page_limit} pages"
            )

        return AdapterScanResult(
            jobs=tuple(jobs),
            warnings=tuple(warnings),
            is_complete_snapshot=complete,
        )

    @staticmethod
    def _require_avature_page(document: HTMLParser) -> None:
        marker = document.css_first('meta[name="avature.portal.page"]')
        if marker is None or marker.attributes.get("content") != "SearchJobs":
            raise AdapterSchemaError("Page is missing Avature SearchJobs metadata")

    def _parse_jobs(self, document: HTMLParser, *, base_url: str) -> tuple[list[RawJob], list[str]]:
        jobs: list[RawJob] = []
        warnings: list[str] = []
        for index, article in enumerate(document.css("article.article--result")):
            anchor = article.css_first('h3 a.link[href*="/JobDetail/"]')
            if anchor is None:
                warnings.append(f"Avature job card {index} is missing its link; skipped")
                continue
            title = self._text(anchor)
            source_url = urljoin(base_url, anchor.attributes.get("href", ""))
            path_parts = [part for part in urlsplit(source_url).path.split("/") if part]
            source_job_id = path_parts[-1] if path_parts else ""
            if not title or not source_job_id:
                warnings.append(f"Avature job card {index} is missing title or source id; skipped")
                continue
            location_node = article.css_first(".list-item-location")
            location = self._text(location_node) if location_node else ""
            location = re.sub(r"\s+,\s+", ", ", location)
            country_node = article.css_first(".list-item-jobCountry")
            city_node = article.css_first(".list-item-jobCity")
            posted_node = article.css_first(".list-item-posted")
            jobs.append(
                RawJob(
                    source=self.name,
                    source_job_id=source_job_id,
                    source_url=source_url,
                    apply_url=source_url,
                    title=title,
                    location=location,
                    country=self._text(country_node) or None,
                    city=self._text(city_node) or None,
                    posted_at=self._posted_at(self._text(posted_node)),
                    ats_job_id=source_job_id,
                    requisition_id=source_job_id,
                    raw_payload={"href": anchor.attributes.get("href", "")},
                )
            )
        return jobs, warnings

    @classmethod
    def _expected_total(cls, document: HTMLParser) -> tuple[int | None, bool]:
        node = document.css_first(".list-controls__text__legend[aria-label]")
        if node is None:
            return None, False
        match = cls._TOTAL.search(node.attributes.get("aria-label", ""))
        if match is None:
            return None, False
        return int(match.group("count")), match.group("plus") is None

    @staticmethod
    def _next_url(document: HTMLParser, *, base_url: str) -> str | None:
        node = document.css_first("a.paginationNextLink[href]")
        if node is None:
            node = document.css_first(".paginationNextLink a[href]")
        if node is None:
            return None
        result = urljoin(base_url, node.attributes.get("href", ""))
        if urlsplit(result).hostname != urlsplit(base_url).hostname:
            raise AdapterSchemaError(f"Avature next link changes host: {result}")
        return result

    @staticmethod
    def _text(node: Node | None) -> str:
        if node is None:
            return ""
        return " ".join(node.text(separator=" ").split())

    @staticmethod
    def _posted_at(value: str) -> datetime | None:
        parsed = parse_datetime(value)
        if parsed is not None:
            return parsed
        try:
            return datetime.strptime(value, "%d-%b-%Y").replace(tzinfo=UTC)
        except ValueError:
            return None
