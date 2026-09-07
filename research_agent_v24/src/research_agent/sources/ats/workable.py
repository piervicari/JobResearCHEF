"""Workable widget-API adapter (single-request catalog, inline detail).

Protocol provenance (MIT, reference only — no external code runs here):
- ats-scrapers @ 6b44a1b (scrapers/workable.py): widget endpoint, shortcode
  native ID, multi-location row combining, Markdown-detail concept.
- ats-jobs @ 9edd4a6 (src/providers.js WORKABLE): `?details=true` variant.

Live evidence (Wave 1.1, sequential, JobResearCHEF HttpFetcher):
- `apply.workable.com/api/v1/widget/accounts/starling-bank`: 200,
  104 rows; `?details=true`: 200, same 104 rows / same 49 shortcodes,
  full HTML description inline on all 104 rows → INLINE_DETAIL_CONFIRMED.
  One catalog request replaces 1 + 49 detail fetches. No N+1 in scan.

Rows repeat per location under one shortcode (104 rows / 49 shortcodes
observed); locations are combined with " | " so one vacancy yields one
RawJob keyed by shortcode. An empty `jobs: []` is NOT authoritative for
Workable (unknown accounts also answer 200+empty): it completes false
with an explicit warning instead of an empty snapshot.
"""

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

_WORKABLE_HOST = "apply.workable.com"


class WorkableAdapter:
    name = "workable"
    bulk_catalog = True

    def supports(self, target: PortalTarget) -> bool:
        return target.host.lower() == _WORKABLE_HOST and any(
            family == "Workable" for family in target.ats_families
        )

    @staticmethod
    def board_token(target: PortalTarget) -> str:
        path_parts = [part for part in urlsplit(target.jobs_search_url).path.split("/") if part]
        if not path_parts:
            raise AdapterSchemaError(
                f"Cannot derive Workable board token from {target.jobs_search_url}"
            )
        return path_parts[0]

    @staticmethod
    def _location(item: dict) -> str:
        locations = item.get("locations")
        if isinstance(locations, list) and locations and isinstance(locations[0], dict):
            first = locations[0]
            joined = ", ".join(
                part
                for part in (
                    string_value(first.get("city")),
                    string_value(first.get("region")),
                    string_value(first.get("country")),
                )
                if part
            )
            if joined:
                return joined
        nested = item.get("location")
        if isinstance(nested, dict) and nested:
            joined = ", ".join(
                part
                for part in (
                    string_value(nested.get("city")),
                    string_value(nested.get("region")),
                    string_value(nested.get("country")),
                )
                if part
            )
            if joined:
                return joined
        return ", ".join(
            part
            for part in (
                string_value(item.get("city")),
                string_value(item.get("state")),
                string_value(item.get("country")),
            )
            if part
        )

    @staticmethod
    def _stable_id(item: dict, index: int) -> str:
        for key in ("shortcode", "code", "id"):
            value = item.get(key)
            if value is not None and str(value).strip():
                return str(value)
        raise AdapterSchemaError(f"Workable jobs[{index}] has no shortcode/code/id")

    async def scan(
        self, target: PortalTarget, context: PortalScanContext
    ) -> AdapterScanResult:
        token = quote(self.board_token(target), safe="")
        api_url = f"https://{_WORKABLE_HOST}/api/v1/widget/accounts/{token}?details=true"
        response = await context.fetch(
            FetchRequest(api_url, headers={"Accept": "application/json"})
        )
        require_success(response)
        payload = require_mapping(response.json(), context="Workable response")
        company_name = string_value(payload.get("name")) or token
        rows = require_list(payload.get("jobs"), context="Workable jobs")
        # One vacancy per shortcode: multi-location rows share it.
        by_id: dict[str, dict] = {}
        order: list[str] = []
        for index, value in enumerate(rows):
            item = require_mapping(value, context=f"Workable jobs[{index}]")
            key = self._stable_id(item, index)
            if key not in by_id:
                by_id[key] = item
                order.append(key)
            else:
                merged = dict(by_id[key])
                merged_location = _combine_locations(
                    self._location(by_id[key]), self._location(item)
                )
                merged["_combined_location"] = merged_location
                by_id[key] = merged
        parsed: list[RawJob] = []
        for key in order:
            item = by_id[key]
            title = string_value(item.get("title"))
            url = string_value(item.get("url")) or string_value(item.get("application_url"))
            if not title or not url:
                raise AdapterSchemaError(
                    f"Workable job {key!r} is missing title or url"
                )
            location = string_value(item.get("_combined_location")) or self._location(item)
            apply_url = string_value(item.get("application_url"))
            parsed.append(
                RawJob(
                    source=self.name,
                    source_job_id=key,
                    source_url=url,
                    apply_url=apply_url or url,
                    title=title,
                    company=company_name,
                    location=location,
                    description=string_value(item.get("description")),
                    posted_at=(
                        parse_datetime(item.get("published_on"))
                        or parse_datetime(item.get("created_at"))
                    ),
                    employment_type=string_value(item.get("type")) or None,
                    ats_job_id=key,
                    raw_payload=item,
                )
            )
        warnings: tuple[str, ...] = ()
        complete = True
        if len(parsed) > context.max_jobs_per_portal:
            parsed = parsed[: context.max_jobs_per_portal]
            complete = False
            warnings = (
                f"Workable response stopped at job cap of {context.max_jobs_per_portal} records",
            )
        elif not parsed:
            # 200 + empty is ambiguous for Workable (unknown accounts answer
            # the same): never an authoritative empty snapshot.
            complete = False
            warnings = (
                "Workable returned zero jobs; empty is ambiguous on this "
                "platform, snapshot not authoritative",
            )
        return AdapterScanResult(
            jobs=tuple(parsed), warnings=warnings, is_complete_snapshot=complete
        )


def _combine_locations(*values: str) -> str:
    seen: dict[str, None] = {}
    for value in values:
        for part in (value or "").split(" | "):
            if part and part not in seen:
                seen[part] = None
    return " | ".join(seen)
