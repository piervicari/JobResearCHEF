"""SAP SuccessFactors Recruiting Marketing server-rendered search adapter."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit

from selectolax.parser import HTMLParser

from research_agent.pipeline.http import FetchRequest
from research_agent.sources.ats.common import AdapterHttpError, AdapterSchemaError
from research_agent.sources.base import (
    AdapterScanResult,
    PortalScanContext,
    PortalTarget,
    RawJob,
)


class SuccessFactorsRmkAdapter:
    name = "successfactors_rmk"
    max_pages = 100
    _SUPPORTED_FAMILY_MARKER = "successfactors recruiting marketing"
    _LOCALE_PATH = re.compile(r"^/[a-z]{2}(?:[-_][a-z]{2})?/?$", re.IGNORECASE)
    _TRAILING_ID = re.compile(r"/(\d+)/?$")

    def supports(self, target: PortalTarget) -> bool:
        return any(
            self._SUPPORTED_FAMILY_MARKER in family.casefold()
            for family in target.ats_families
        )

    @classmethod
    def initial_search_url(cls, target: PortalTarget) -> str:
        parsed = urlsplit(target.jobs_search_url)
        path = parsed.path.rstrip("/")
        if path.casefold().endswith("/search"):
            search_path = f"{path}/"
        elif cls._LOCALE_PATH.fullmatch(parsed.path):
            search_path = f"{path}/search/"
        else:
            search_path = "/search/"
        query = urlencode(
            {
                "q": "",
                "sortColumn": "referencedate",
                "sortDirection": "desc",
                "startrow": 0,
            }
        )
        return urlunsplit((parsed.scheme, parsed.netloc, search_path, query, ""))

    async def scan(
        self, target: PortalTarget, context: PortalScanContext
    ) -> AdapterScanResult:
        next_url: str | None = self.initial_search_url(target)
        seen_pages: set[str] = set()
        seen_jobs: set[str] = set()
        parsed_jobs: list[RawJob] = []
        warnings: list[str] = []
        complete = True

        page_limit = context.page_limit(self.max_pages)
        for page_index in range(page_limit):
            if next_url is None:
                break
            if next_url in seen_pages:
                raise AdapterSchemaError(f"SuccessFactors pagination loop at {next_url}")
            seen_pages.add(next_url)
            response = await context.fetch(
                FetchRequest(next_url, headers={"Accept": "text/html"})
            )
            if not 200 <= response.status_code < 300:
                raise AdapterHttpError(
                    f"HTTP {response.status_code} from SuccessFactors search {next_url}"
                )
            document = HTMLParser(response.text)
            page_jobs = self._parse_jobs(document, base_url=response.final_url)
            if not page_jobs:
                if page_index == 0:
                    warnings.append(
                        "no standard SuccessFactors result rows; snapshot completeness unknown"
                    )
                    complete = False
                    break
                raise AdapterSchemaError(
                    f"SuccessFactors linked page {page_index + 1} has no standard result rows"
                )
            for job in page_jobs:
                if job.apply_url in seen_jobs:
                    continue
                seen_jobs.add(job.apply_url)
                parsed_jobs.append(job)
            current_start = _start_row(response.final_url)
            next_url = self._next_page_url(
                document,
                base_url=response.final_url,
                current_start=current_start,
            )
            if len(parsed_jobs) > context.max_jobs_per_portal or (
                len(parsed_jobs) == context.max_jobs_per_portal and next_url is not None
            ):
                parsed_jobs = parsed_jobs[: context.max_jobs_per_portal]
                complete = False
                warnings.append(
                    "SuccessFactors pagination stopped at job cap of "
                    f"{context.max_jobs_per_portal} records"
                )
                break
        else:
            complete = False
            warnings.append(
                f"SuccessFactors pagination stopped at safety cap of {page_limit} pages"
            )

        return AdapterScanResult(
            jobs=tuple(parsed_jobs),
            warnings=tuple(warnings),
            is_complete_snapshot=complete,
        )

    def _parse_jobs(self, document: HTMLParser, *, base_url: str) -> list[RawJob]:
        jobs: list[RawJob] = []
        rows = document.css("tr.data-row")
        tiled_layout = not rows
        if tiled_layout:
            rows = document.css("li.job-tile")
        for index, row in enumerate(rows):
            title_node = row.css_first("a.jobTitle-link")
            if title_node is None:
                raise AdapterSchemaError(
                    f"SuccessFactors result row {index} is missing a.jobTitle-link"
                )
            href = title_node.attributes.get("href", "").strip()
            title = " ".join(title_node.text(separator=" ").split())
            if not href or not title:
                raise AdapterSchemaError(
                    f"SuccessFactors result row {index} is missing title or href"
                )
            job_url = urljoin(base_url, href)
            location_selector = (
                ".sub-section-desktop div.section-field.location > div"
                if tiled_layout
                else "td.colLocation .jobLocation"
            )
            location_node = row.css_first(location_selector)
            location = (
                " ".join(location_node.text(separator=" ").split())
                if location_node is not None
                else ""
            )
            matched_id = self._TRAILING_ID.search(urlsplit(job_url).path)
            source_job_id = matched_id.group(1) if matched_id else job_url
            jobs.append(
                RawJob(
                    source=self.name,
                    source_job_id=source_job_id,
                    source_url=job_url,
                    apply_url=job_url,
                    title=title,
                    location=location,
                    ats_job_id=source_job_id,
                    requisition_id=source_job_id,
                    raw_payload={"title": title, "location": location, "url": job_url},
                )
            )
        return jobs

    @staticmethod
    def _next_page_url(
        document: HTMLParser, *, base_url: str, current_start: int
    ) -> str | None:
        candidates: list[tuple[int, str]] = []
        for anchor in document.css("a[href]"):
            absolute = urljoin(base_url, anchor.attributes.get("href", ""))
            start = _start_row(absolute)
            if start > current_start:
                candidates.append((start, absolute))
        if not candidates:
            return None
        return min(candidates, key=lambda item: item[0])[1]


def _start_row(url: str) -> int:
    raw = parse_qs(urlsplit(url).query).get("startrow", ["0"])[0]
    try:
        return int(raw)
    except ValueError:
        return 0
