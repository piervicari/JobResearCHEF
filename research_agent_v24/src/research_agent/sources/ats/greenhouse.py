"""Greenhouse public Job Board API adapter.

Wave 2.1 parser reuse (ats-scrapers @ 6b44a1b, ats-jobs @ 9edd4a6, MIT):
departments/offices/metadata/internal_job_id ride along in the full
`raw_payload` (no house department field exists — same precedent as the
Teamtailor decision); `content` is unescaped once from its double-encoded
form (downstream `normalize_job`/`html_to_text` finishes the job);
placeholder requisition strings are filtered. Strict shape guards and
source identity (`id`) are unchanged.
"""

from __future__ import annotations

import html as html_mod
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
                    description=_unescape_content(job.get("content")),
                    posted_at=(
                        parse_datetime(job.get("first_published"))
                        or parse_datetime(job.get("updated_at"))
                    ),
                    ats_job_id=str(job_id),
                    requisition_id=_requisition_id(job.get("requisition_id")),
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


# Placeholder requisition strings employers leave in the field (ats-scrapers
# protocol knowledge). Only real identifiers are kept.
_REQUISITION_PLACEHOLDERS = frozenset({"see opening id", "tbd", "n/a", "tba"})


def _requisition_id(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in _REQUISITION_PLACEHOLDERS:
        return None
    return text


def _unescape_content(value: object) -> str:
    """Unescape Greenhouse's double-encoded `content` once.

    `&lt;div&gt;` becomes real HTML; content without entities is returned
    unchanged (unescape is identity there), so no meaningful content is
    double-transformed. Downstream `html_to_text` strips tags and unescapes
    the second layer.
    """
    text = string_value(value)
    if not text:
        return ""
    return html_mod.unescape(text)
