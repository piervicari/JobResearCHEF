"""Teamtailor JSON-feed adapter (single-request catalog).

Protocol provenance (MIT, reference only — no external code runs here):
- ats-scrapers @ 6b44a1b (scrapers/teamtailor.py): tenant subdomain RSS
  catalog, numeric-ID-from-URL rule, shape-guard philosophy.
- ats-jobs @ 9edd4a6 (src/providers.js TEAMTAILOR): `/jobs.json` feed
  (`items[]` with `content_html` + schema.org `_jobposting`).

Live evidence (Wave 1.1, sequential, JobResearCHEF HttpFetcher):
- `polestar.teamtailor.com/jobs.rss`: 200, 27 jobs parsed.
- `polestar.teamtailor.com/jobs.json`: 200, 27 items, same vacancy set
  (titles/URLs match), richer bodies. JSON selected: equivalent catalog,
  simpler parsing, no XML namespaces. RSS kept as fallback knowledge only.

Single GET returns the whole catalog (no pagination). Description is
inline (`content_html`, raw HTML stored like Greenhouse `content`).
A 200 with valid JSON shape proves the tenant, so `items: []` is a valid
empty snapshot; non-2xx (e.g. 404 wrong tenant) never is.
"""

from __future__ import annotations

import re
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

_TEAMTAILOR_SUFFIX = ".teamtailor.com"
# Stable native ID lives in the public URL: /jobs/{numeric}-{slug}.
_URL_ID_RE = re.compile(r"/jobs/(\d+)")


class TeamtailorAdapter:
    name = "teamtailor"
    bulk_catalog = True

    def supports(self, target: PortalTarget) -> bool:
        host = target.host.lower()
        if host.endswith(_TEAMTAILOR_SUFFIX):
            return True
        # Tenants on their own domain: family label decides, no probing.
        return any(family == "Teamtailor" for family in target.ats_families)

    @staticmethod
    def _base_and_slug(target: PortalTarget) -> tuple[str, str]:
        host = target.host.lower()
        if host.endswith(_TEAMTAILOR_SUFFIX):
            slug = host[: -len(_TEAMTAILOR_SUFFIX)]
            if not slug or "." in slug:
                raise AdapterSchemaError(
                    f"Cannot derive Teamtailor tenant from {target.jobs_search_url}"
                )
            return f"{slug}.teamtailor.com", slug
        return host, host

    @staticmethod
    def _native_id(item: dict, url: str, index: int) -> str:
        match = _URL_ID_RE.search(url)
        if match:
            return match.group(1)
        fallback = string_value(item.get("id"))
        if fallback:
            return fallback
        raise AdapterSchemaError(f"Teamtailor items[{index}] has no stable id or url")

    @staticmethod
    def _location(posting: object) -> str:
        if not isinstance(posting, dict):
            return ""
        job_location = posting.get("jobLocation", {})
        if isinstance(job_location, list):
            job_location = next(
                (entry for entry in job_location if isinstance(entry, dict)), {}
            )
        address = job_location.get("address", {}) if isinstance(job_location, dict) else {}
        if not isinstance(address, dict):
            return ""
        parts = [
            string_value(address.get("addressLocality")),
            string_value(address.get("addressRegion")),
            string_value(address.get("addressCountry")),
        ]
        return ", ".join(part for part in parts if part)

    async def scan(
        self, target: PortalTarget, context: PortalScanContext
    ) -> AdapterScanResult:
        base, slug = self._base_and_slug(target)
        api_url = f"https://{quote(base, safe='')}/jobs.json"
        _ = slug
        response = await context.fetch(
            FetchRequest(api_url, headers={"Accept": "application/json"})
        )
        require_success(response)
        payload = require_mapping(response.json(), context="Teamtailor response")
        items = require_list(payload.get("items"), context="Teamtailor items")
        parsed: list[RawJob] = []
        seen: set[str] = set()
        for index, value in enumerate(items):
            job = require_mapping(value, context=f"Teamtailor items[{index}]")
            title = string_value(job.get("title"))
            url = string_value(job.get("url"))
            if not title or not url:
                raise AdapterSchemaError(
                    f"Teamtailor items[{index}] is missing title or url"
                )
            native_id = self._native_id(job, url, index)
            if native_id in seen:
                continue
            seen.add(native_id)
            posting = job.get("_jobposting")
            posting = posting if isinstance(posting, dict) else {}
            parsed.append(
                RawJob(
                    source=self.name,
                    source_job_id=native_id,
                    source_url=url,
                    apply_url=url,
                    title=title,
                    location=self._location(posting),
                    description=string_value(job.get("content_html")),
                    posted_at=(
                        parse_datetime(job.get("date_published"))
                        or parse_datetime(posting.get("datePosted"))
                    ),
                    employment_type=string_value(posting.get("employmentType")) or None,
                    ats_job_id=native_id,
                    raw_payload=job,
                )
            )
        warnings: tuple[str, ...] = ()
        complete = True
        if len(parsed) > context.max_jobs_per_portal:
            parsed = parsed[: context.max_jobs_per_portal]
            complete = False
            warnings = (
                f"Teamtailor response stopped at job cap of {context.max_jobs_per_portal} records",
            )
        elif not parsed:
            warnings = ("upstream reports zero active jobs",)
        return AdapterScanResult(
            jobs=tuple(parsed), warnings=warnings, is_complete_snapshot=complete
        )
