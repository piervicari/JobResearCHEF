"""Google Careers anonymous BOQ ``batchexecute`` adapter.

Google's public Careers result pages are server-rendered, but the same frontend exposes a
structured anonymous RPC used by pagination.  This adapter replays that RPC instead of
crawling HTML result/detail pages.  The contract is positional and therefore deliberately
pinned by tests.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from urllib.parse import urlsplit

from research_agent.pipeline.http import FetchRequest
from research_agent.sources.ats.common import AdapterHttpError, AdapterSchemaError
from research_agent.sources.base import AdapterScanResult, PortalScanContext, PortalTarget, RawJob


class GoogleCareersAdapter:
    name = "google_careers_rpc"
    # Structured catalogs may legitimately exceed the generic 500-record HTML cap.
    bulk_catalog = True

    _HOSTS = {"google.com", "www.google.com"}
    _FAMILY = "Custom Google Careers"
    _BASE_PATH = "/about/careers/applications"
    _RESULTS_PATH = f"{_BASE_PATH}/jobs/results"
    _RPC_URL = (
        "https://www.google.com/about/careers/applications/_/"
        "HiringCportalFrontendUi/data/batchexecute"
    )
    _SEARCH_RPC = "r06xKb"
    _PAGE_SIZE = 20
    _ARG_SLOTS = 17
    _ARG_QUERY = 0
    _ARG_LOCALE = 4
    _ARG_PAGE = 7

    # Google job-record slots.  These are not documented field names; pin them in tests.
    _JOB_ID = 0
    _JOB_TITLE = 1
    _JOB_APPLY_URL = 2
    _JOB_RESPONSIBILITIES = 3
    _JOB_QUALIFICATIONS = 4
    _JOB_COMPANY = 7
    _JOB_LOCATIONS = 9
    _JOB_DESCRIPTION = 10
    _JOB_CREATED_TS = 12
    _JOB_UPDATED_TS = 13
    _JOB_MIN_QUALIFICATIONS = 19

    def supports(self, target: PortalTarget) -> bool:
        parsed = urlsplit(target.jobs_search_url)
        return (
            target.host.casefold() in self._HOSTS
            and parsed.path.rstrip("/").startswith(self._RESULTS_PATH)
            and any(family == self._FAMILY for family in target.ats_families)
        )

    async def scan(self, target: PortalTarget, context: PortalScanContext) -> AdapterScanResult:
        collected: list[RawJob] = []
        seen_ids: set[str] = set()
        total: int | None = None
        warnings: list[str] = []
        page_limit = context.page_limit(10_000)

        for page in range(1, page_limit + 1):
            inner = await self._search_page(context, page=page)
            jobs, page_total = self._parse_search_payload(inner, page=page)
            if total is None:
                total = page_total
            elif page_total != total:
                warnings.append(
                    f"Google Careers reported total changed during scan: {total} -> {page_total}"
                )
                total = max(total, page_total)

            if not jobs:
                # An empty page is safe only after the reported inventory has been collected.
                if total is not None and len(collected) >= total:
                    break
                raise AdapterSchemaError(
                    f"Google Careers page {page} returned no jobs before reported total {total}"
                )

            for record in jobs:
                raw = self._parse_job(record)
                if raw.source_job_id in seen_ids:
                    continue
                seen_ids.add(raw.source_job_id)
                collected.append(raw)
                if len(collected) >= context.max_jobs_per_portal:
                    warnings.append(
                        "Google Careers response stopped at job cap of "
                        f"{context.max_jobs_per_portal} records"
                    )
                    return AdapterScanResult(
                        jobs=tuple(collected[: context.max_jobs_per_portal]),
                        warnings=tuple(warnings),
                        is_complete_snapshot=False,
                    )

            if total is not None and len(collected) >= total:
                break
            if len(jobs) < self._PAGE_SIZE:
                break

        reported_total = total or 0
        complete = reported_total == len(collected)
        if reported_total == 0 and not collected:
            warnings.append("upstream reports zero active jobs")
            complete = True
        elif not complete:
            expected_pages = math.ceil(reported_total / self._PAGE_SIZE) if reported_total else None
            warnings.append(
                "Google Careers snapshot incomplete: "
                f"collected={len(collected)} reported_total={reported_total} "
                f"page_limit={page_limit} expected_pages={expected_pages}"
            )

        return AdapterScanResult(
            jobs=tuple(collected),
            warnings=tuple(warnings),
            is_complete_snapshot=complete,
        )

    async def _search_page(self, context: PortalScanContext, *, page: int) -> object:
        response = await context.fetch(
            FetchRequest(
                self._RPC_URL,
                method="POST",
                allow_cache=False,
                headers={
                    "Accept": "*/*",
                    "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                },
                form_body={"f.req": self._build_f_req(self._SEARCH_RPC, self._build_search_args(page))},
            )
        )
        if not 200 <= response.status_code < 300:
            raise AdapterHttpError(
                f"HTTP {response.status_code} from Google Careers RPC"
            )
        inner = self._decode_response(response.text)
        if inner is None:
            raise AdapterSchemaError(
                f"Google Careers RPC page {page} returned no decodable payload"
            )
        return inner

    @classmethod
    def _build_search_args(cls, page: int) -> list[object]:
        slots: list[object] = [None] * cls._ARG_SLOTS
        slots[cls._ARG_QUERY] = None
        slots[cls._ARG_LOCALE] = "en-US"
        slots[cls._ARG_PAGE] = max(1, page)
        return [slots]

    @staticmethod
    def _build_f_req(rpc: str, args: list[object]) -> str:
        return json.dumps([[[rpc, json.dumps(args), None, "generic"]]], separators=(",", ":"))

    @staticmethod
    def _decode_response(raw: str) -> object | None:
        # batchexecute may prepend XSSI and length lines.  Find the actual envelope line.
        for line in (raw or "").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(")]}'") or not stripped.startswith('[["wrb.fr"'):
                continue
            try:
                envelope = json.loads(stripped)
                payload = envelope[0][2]
                return json.loads(payload) if payload else None
            except (json.JSONDecodeError, IndexError, TypeError):
                continue
        return None

    @staticmethod
    def _parse_search_payload(inner: object, *, page: int) -> tuple[list[list[object]], int]:
        if not isinstance(inner, list) or not inner:
            raise AdapterSchemaError(f"Google Careers page {page} payload is not a non-empty list")
        raw_jobs = inner[0]
        if raw_jobs is None:
            return [], 0
        if not isinstance(raw_jobs, list):
            raise AdapterSchemaError(f"Google Careers page {page} jobs field is not a list")
        jobs = [item for item in raw_jobs if isinstance(item, list)]
        if len(jobs) != len(raw_jobs):
            raise AdapterSchemaError(f"Google Careers page {page} contains malformed job records")
        total = inner[2] if len(inner) > 2 else None
        if not isinstance(total, int) or total < 0:
            raise AdapterSchemaError(f"Google Careers page {page} is missing a valid total")
        return jobs, total

    @classmethod
    def _parse_job(cls, job: list[object]) -> RawJob:
        job_id = cls._string_at(job, cls._JOB_ID)
        title = cls._string_at(job, cls._JOB_TITLE)
        if not job_id or not title:
            raise AdapterSchemaError("Google Careers job record is missing id or title")

        public_url = f"https://www.google.com{cls._RESULTS_PATH}/{job_id}"
        apply_url = cls._string_at(job, cls._JOB_APPLY_URL) or public_url
        company = cls._string_at(job, cls._JOB_COMPANY)
        location_names, city, country = cls._locations(job)

        sections: list[tuple[str, str]] = []
        for heading, index in (
            ("Description", cls._JOB_DESCRIPTION),
            ("Responsibilities", cls._JOB_RESPONSIBILITIES),
            ("Qualifications", cls._JOB_QUALIFICATIONS),
            ("Minimum qualifications", cls._JOB_MIN_QUALIFICATIONS),
        ):
            value = cls._html_at(job, index)
            if value and value not in {body for _, body in sections}:
                sections.append((heading, value))
        description = "\n".join(f"<h2>{heading}</h2>{body}" for heading, body in sections)

        posted_at = cls._timestamp_at(job, cls._JOB_CREATED_TS)
        updated_at = cls._timestamp_at(job, cls._JOB_UPDATED_TS)
        return RawJob(
            source=cls.name,
            source_job_id=job_id,
            source_url=public_url,
            apply_url=apply_url,
            title=title,
            company=company,
            location="; ".join(location_names),
            country=country,
            city=city,
            description=description,
            posted_at=posted_at or updated_at,
            ats_job_id=job_id,
            raw_payload={"record": job},
        )

    @staticmethod
    def _string_at(job: list[object], index: int) -> str:
        if index >= len(job):
            return ""
        value = job[index]
        return value.strip() if isinstance(value, str) else ""

    @staticmethod
    def _html_at(job: list[object], index: int) -> str:
        if index >= len(job):
            return ""
        value = job[index]
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list) and len(value) > 1 and isinstance(value[1], str):
            return value[1].strip()
        return ""

    @staticmethod
    def _timestamp_at(job: list[object], index: int) -> datetime | None:
        if index >= len(job):
            return None
        value = job[index]
        if not isinstance(value, list) or not value or not isinstance(value[0], (int, float)):
            return None
        try:
            return datetime.fromtimestamp(value[0], UTC)
        except (OverflowError, OSError, ValueError):
            return None

    @classmethod
    def _locations(cls, job: list[object]) -> tuple[list[str], str | None, str | None]:
        if cls._JOB_LOCATIONS >= len(job) or not isinstance(job[cls._JOB_LOCATIONS], list):
            return [], None, None
        entries = job[cls._JOB_LOCATIONS]
        names: list[str] = []
        parsed: list[tuple[str | None, str | None]] = []
        for entry in entries:
            if not isinstance(entry, list):
                continue
            if entry and isinstance(entry[0], str) and entry[0].strip() and entry[0].strip() not in names:
                names.append(entry[0].strip())
            city = entry[2].strip() if len(entry) > 2 and isinstance(entry[2], str) and entry[2].strip() else None
            country = entry[5].strip() if len(entry) > 5 and isinstance(entry[5], str) and entry[5].strip() else None
            parsed.append((city, country))
        # Do not pretend one city/country describes a multi-location vacancy.
        if len(parsed) == 1:
            return names, parsed[0][0], parsed[0][1]
        return names, None, None
