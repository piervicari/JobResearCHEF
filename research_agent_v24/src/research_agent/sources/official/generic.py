"""Conservative official HTML fallback with robots.txt enforcement."""

from __future__ import annotations

import hashlib
import json
import re
import urllib.robotparser
from collections.abc import Iterable
from urllib.parse import urljoin, urlsplit, urlunsplit

from selectolax.parser import HTMLParser

from research_agent.pipeline.dedup import canonical_application_url
from research_agent.pipeline.http import FetchRequest
from research_agent.sources.ats.common import (
    AdapterHttpError,
    AdapterSchemaError,
    parse_datetime,
    string_value,
)
from research_agent.sources.base import (
    AdapterScanResult,
    PortalScanContext,
    PortalTarget,
    RawJob,
)


class RobotsDisallowed(AdapterHttpError):
    pass


class GenericOfficialHtmlAdapter:
    name = "official_html"
    user_agent_token = "research-agent-pier"
    _JOB_PATH_PATTERN = re.compile(
        r"(?:/jobs?/|/job-detail/|/jobdetail/|/positions?/|[?&](?:gh_jid|jobId)=)",
        re.IGNORECASE,
    )
    _GENERIC_ANCHOR_TEXT = {
        "apply",
        "apply now",
        "careers",
        "jobs",
        "find jobs",
        "find a job",
        "job openings",
        "learn more",
        "read more",
        "search jobs",
        "view job",
        "view jobs",
    }

    def supports(self, target: PortalTarget) -> bool:
        return urlsplit(target.jobs_search_url).scheme.lower() in {"http", "https"}

    async def scan(self, target: PortalTarget, context: PortalScanContext) -> AdapterScanResult:
        await self._enforce_robots(target, context)
        response = await context.fetch(FetchRequest(target.jobs_search_url))
        if not 200 <= response.status_code < 300:
            raise AdapterHttpError(
                f"HTTP {response.status_code} from official portal {target.jobs_search_url}"
            )
        content_type = response.headers.get("content-type", "")
        if "html" not in content_type.casefold() and not response.text.lstrip().startswith("<"):
            raise AdapterSchemaError(
                f"Generic official adapter expected HTML from {target.jobs_search_url}"
            )
        document = HTMLParser(response.text)
        jobs = self._json_ld_jobs(document, base_url=response.final_url)
        warnings: list[str] = []
        if not jobs:
            jobs = self._anchor_jobs(document, base_url=response.final_url)
            if jobs:
                warnings.append("anchor discovery only; details require targeted enrichment")
        if not jobs:
            warnings.append("no JSON-LD JobPosting or high-confidence job links found")
        complete = False
        if len(jobs) > context.max_jobs_per_portal:
            jobs = jobs[: context.max_jobs_per_portal]
            warnings.append(
                f"generic discovery stopped at job cap of {context.max_jobs_per_portal} records"
            )
        return AdapterScanResult(
            jobs=tuple(jobs), warnings=tuple(warnings), is_complete_snapshot=complete
        )

    async def _enforce_robots(self, target: PortalTarget, context: PortalScanContext) -> None:
        parsed = urlsplit(target.jobs_search_url)
        robots_url = urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))
        response = await context.fetch(
            FetchRequest(robots_url, headers={"Accept": "text/plain,*/*;q=0.1"})
        )
        if response.status_code == 404:
            return
        if response.status_code in {401, 403}:
            raise RobotsDisallowed(f"robots.txt access denied at {robots_url}")
        if not 200 <= response.status_code < 300:
            raise AdapterHttpError(f"robots.txt returned HTTP {response.status_code}")
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(response.text.splitlines())
        if not parser.can_fetch(self.user_agent_token, target.jobs_search_url):
            raise RobotsDisallowed(f"robots.txt disallows {target.jobs_search_url}")

    def _json_ld_jobs(self, document: HTMLParser, *, base_url: str) -> list[RawJob]:
        jobs: list[RawJob] = []
        seen_urls: set[str] = set()
        for node in document.css('script[type="application/ld+json"]'):
            try:
                payload = json.loads(node.text())
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            for item in _walk_json_ld(payload):
                if not _is_job_posting(item):
                    continue
                parsed = self._parse_json_ld_job(item, base_url=base_url)
                if parsed is None:
                    continue
                canonical_url = canonical_application_url(parsed.apply_url)
                if canonical_url in seen_urls:
                    continue
                seen_urls.add(canonical_url)
                jobs.append(parsed)
        return jobs

    def _parse_json_ld_job(self, item: dict[str, object], *, base_url: str) -> RawJob | None:
        title = string_value(item.get("title"))
        raw_url = string_value(item.get("url"))
        if not raw_url:
            raw_url = string_value(item.get("sameAs"))
        job_url = urljoin(base_url, raw_url)
        if not title or not job_url:
            return None

        identifier = item.get("identifier")
        source_job_id = ""
        if isinstance(identifier, dict):
            source_job_id = string_value(identifier.get("value"))
        elif isinstance(identifier, str):
            source_job_id = identifier.strip()
        source_job_id = source_job_id or canonical_application_url(job_url)

        hiring = item.get("hiringOrganization") or {}
        company = string_value(hiring.get("name")) if isinstance(hiring, dict) else ""
        location, country, city = _json_ld_location(item)
        remote = string_value(item.get("jobLocationType")).casefold() == "telecommute"
        employment = item.get("employmentType")
        if isinstance(employment, list):
            employment_type = " | ".join(str(value) for value in employment)
        else:
            employment_type = string_value(employment)
        return RawJob(
            source=self.name,
            source_job_id=source_job_id,
            source_url=job_url,
            apply_url=job_url,
            title=title,
            company=company,
            location=location,
            country=country,
            city=city,
            description=string_value(item.get("description")),
            posted_at=parse_datetime(item.get("datePosted")),
            employment_type=employment_type or None,
            workplace_type="remote" if remote else None,
            requisition_id=source_job_id,
            raw_payload=item,
        )

    def _anchor_jobs(self, document: HTMLParser, *, base_url: str) -> list[RawJob]:
        jobs: list[RawJob] = []
        seen_urls: set[str] = set()
        for anchor in document.css("a[href]"):
            href = (anchor.attributes.get("href") or "").strip()
            absolute_url = urljoin(base_url, href)
            if not self._JOB_PATH_PATTERN.search(absolute_url):
                continue
            title = " ".join(anchor.text(separator=" ").split())
            if len(title) < 4 or len(title) > 200 or title.casefold() in self._GENERIC_ANCHOR_TEXT:
                continue
            canonical_url = canonical_application_url(absolute_url)
            if not canonical_url or canonical_url in seen_urls:
                continue
            seen_urls.add(canonical_url)
            jobs.append(
                RawJob(
                    source=self.name,
                    source_job_id=hashlib.sha256(canonical_url.encode("utf-8")).hexdigest(),
                    source_url=absolute_url,
                    apply_url=absolute_url,
                    title=title,
                    raw_payload={"href": href, "anchor_text": title},
                )
            )
        return jobs


def _walk_json_ld(value: object) -> Iterable[dict[str, object]]:
    if isinstance(value, list):
        for item in value:
            yield from _walk_json_ld(item)
    elif isinstance(value, dict):
        graph = value.get("@graph")
        if graph is not None:
            yield from _walk_json_ld(graph)
        yield value


def _is_job_posting(item: dict[str, object]) -> bool:
    item_type = item.get("@type")
    if isinstance(item_type, list):
        return any(str(value).casefold() == "jobposting" for value in item_type)
    return str(item_type).casefold() == "jobposting"


def _json_ld_location(item: dict[str, object]) -> tuple[str, str | None, str | None]:
    locations = item.get("jobLocation")
    if not isinstance(locations, list):
        locations = [locations] if locations is not None else []
    display_values: list[str] = []
    countries: list[str] = []
    cities: list[str] = []
    for location in locations:
        if not isinstance(location, dict):
            continue
        address = location.get("address") or {}
        if not isinstance(address, dict):
            continue
        city = string_value(address.get("addressLocality"))
        region = string_value(address.get("addressRegion"))
        country = string_value(address.get("addressCountry"))
        display = ", ".join(value for value in (city, region, country) if value)
        if display:
            display_values.append(display)
        if country:
            countries.append(country)
        if city:
            cities.append(city)
    unique_countries = tuple(dict.fromkeys(countries))
    unique_cities = tuple(dict.fromkeys(cities))
    return (
        " | ".join(dict.fromkeys(display_values)),
        unique_countries[0] if len(unique_countries) == 1 else None,
        unique_cities[0] if len(unique_cities) == 1 else None,
    )
