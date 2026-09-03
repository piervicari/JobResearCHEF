"""Radancy/TalentBrew server-rendered search adapter for verified public hosts."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from selectolax.parser import HTMLParser, Node

from research_agent.pipeline.http import FetchRequest
from research_agent.sources.ats.common import AdapterSchemaError, require_success
from research_agent.sources.base import (
    AdapterScanResult,
    PortalScanContext,
    PortalTarget,
    RawJob,
)


class RadancyAdapter:
    name = "radancy_talentbrew"
    max_pages = 100
    verified_hosts = {
        "careers.blackrock.com",
        "jobs.appliedmaterials.com",
        "jobs.boeing.com",
        "jobs.disneycareers.com",
        "jobs.ikea.com",
        "jobs.intuit.com",
        "jobs.paloaltonetworks.com",
    }
    _TITLE_SELECTORS = (
        ".search-results__job-title",
        ".section29__search-results-job-title",
        ".job-list__title",
        "h2",
        "h3",
    )
    _LOCATION_SELECTORS = (
        ".job-location",
        ".search-results__job-info.location",
        ".section29__result-location",
        ".job-list__location",
        ".location",
    )

    def supports(self, target: PortalTarget) -> bool:
        path = urlsplit(target.jobs_search_url).path.casefold()
        return target.host.casefold() in self.verified_hosts and (
            "search-jobs" in path or "search_jobs" in path
        )

    async def scan(self, target: PortalTarget, context: PortalScanContext) -> AdapterScanResult:
        jobs: list[RawJob] = []
        seen_jobs: set[str] = set()
        warnings: list[str] = []
        expected_total: int | None = None
        expected_pages: int | None = None
        complete = True
        page_limit = context.page_limit(self.max_pages)

        for page in range(1, page_limit + 1):
            url = target.jobs_search_url if page == 1 else _page_url(target.jobs_search_url, page)
            response = await context.fetch(
                FetchRequest(url, headers={"Accept": "text/html"})
            )
            require_success(response)
            page_jobs, total, total_pages, current_page, page_warnings = self._parse_page(
                response.text,
                base_url=response.final_url,
            )
            warnings.extend(page_warnings)
            if current_page != page:
                raise AdapterSchemaError(
                    f"Radancy requested page {page} but response reports page {current_page}"
                )
            if expected_total is None:
                expected_total = total
                expected_pages = total_pages
            elif total != expected_total:
                warnings.append(
                    f"Radancy total changed during pagination: {expected_total} -> {total}"
                )
            for job in page_jobs:
                if job.source_job_id in seen_jobs:
                    continue
                seen_jobs.add(job.source_job_id)
                jobs.append(job)
            if len(jobs) >= context.max_jobs_per_portal and len(jobs) < total:
                jobs = jobs[: context.max_jobs_per_portal]
                complete = False
                warnings.append(
                    f"Radancy pagination stopped at job cap of "
                    f"{context.max_jobs_per_portal} records"
                )
                break
            if len(jobs) >= total:
                break
            if page >= total_pages:
                complete = False
                warnings.append(f"Radancy pagination ended at {len(jobs)} of {total} jobs")
                break
        else:
            complete = False
            warnings.append(f"Radancy pagination stopped at safety cap of {page_limit} pages")

        if expected_total == 0:
            warnings.append("upstream reports zero active jobs")
        if expected_total is None or expected_pages is None:
            raise AdapterSchemaError("Radancy search returned no pagination metadata")
        return AdapterScanResult(
            jobs=tuple(jobs),
            warnings=tuple(dict.fromkeys(warnings)),
            is_complete_snapshot=complete and len(jobs) == expected_total,
        )

    def _parse_page(
        self,
        html: str,
        *,
        base_url: str,
    ) -> tuple[list[RawJob], int, int, int, list[str]]:
        document = HTMLParser(html)
        search = document.css_first("#search-results")
        if search is None:
            raise AdapterSchemaError("Radancy page is missing #search-results")
        total = _integer_attribute(search, "data-total-job-results")
        total_pages = _integer_attribute(search, "data-total-pages")
        current_page = _integer_attribute(search, "data-current-page")
        warnings: list[str] = []
        jobs: list[RawJob] = []
        seen: set[str] = set()
        for index, anchor in enumerate(
            document.css('#search-results-list a[href][data-job-id]')
        ):
            source_job_id = anchor.attributes.get("data-job-id", "").strip()
            if not source_job_id or source_job_id in seen:
                continue
            title = _first_text(anchor, self._TITLE_SELECTORS)
            href = anchor.attributes.get("href", "").strip()
            if not title or not href:
                warnings.append(f"Radancy job card {index} is incomplete; skipped")
                continue
            seen.add(source_job_id)
            job_url = urljoin(base_url, href)
            jobs.append(
                RawJob(
                    source=self.name,
                    source_job_id=source_job_id,
                    source_url=job_url,
                    apply_url=job_url,
                    title=title,
                    location=_first_text(anchor, self._LOCATION_SELECTORS),
                    employment_type=_first_text(anchor, (".job-list__job-type",)) or None,
                    ats_job_id=source_job_id,
                    requisition_id=source_job_id,
                    raw_payload={"href": href, "page": current_page},
                )
            )
        if total > 0 and not jobs:
            raise AdapterSchemaError(
                "Radancy search reports jobs but contains no parseable result cards"
            )
        return jobs, total, total_pages, current_page, warnings


def _integer_attribute(node: Node, name: str) -> int:
    value = node.attributes.get(name, "").strip()
    try:
        parsed = int(value)
    except ValueError as exc:
        raise AdapterSchemaError(f"Radancy search has invalid {name}: {value!r}") from exc
    if parsed < 0:
        raise AdapterSchemaError(f"Radancy search has negative {name}: {parsed}")
    return parsed


def _first_text(node: Node, selectors: tuple[str, ...]) -> str:
    for selector in selectors:
        candidate = node.css_first(selector)
        if candidate is not None:
            text = " ".join(candidate.text(separator=" ").split())
            if text:
                return text
    return ""


def _page_url(url: str, page: int) -> str:
    parts = urlsplit(url)
    query = [(key, value) for key, value in parse_qsl(parts.query) if key != "p"]
    query.append(("p", str(page)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
