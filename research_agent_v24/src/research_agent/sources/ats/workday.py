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
    # Known provider result cap: capped tenants report total == 2000 exactly
    # and pagination past offset 2000 wraps to page 1 (Stapply ats-scrapers
    # v0.3.0 evidence). A catalog sitting exactly on this cap MUST NOT
    # complete without facet subdivision (Phase B, below).
    PROVIDER_RESULT_CAP = 2000
    CAPPED_TOTAL_WARNING = (
        "Workday catalog total equals the provider result cap (2000); "
        "snapshot kept bounded until facet subdivision reconciles it"
    )
    # Static Phase-B subdivision dimensions (Stapply-proven order). Phase C
    # (counts-based selection) is deferred; this order is fixed.
    _SUBDIVISION_DIMENSIONS = ("jobFamilyGroup", "timeType", "locations", "workerSubType")
    SUBDIVISION_ACTIVATED_WARNING = (
        "Workday facet subdivision activated: root catalog at provider cap (2000)"
    )
    BRANCH_UNRESOLVED_WARNING = (
        "Workday facet branch remains capped after available dimensions; "
        "snapshot kept bounded"
    )
    BRANCH_FAILED_WARNING = (
        "Workday facet branch failed; collected jobs kept, snapshot bounded"
    )
    SUBDIVISION_BUDGET_WARNING = (
        "Workday facet subdivision exhausted the page budget; snapshot kept bounded"
    )
    DUPLICATE_BRANCH_WARNING = (
        "Workday facet branch repeats an already-visited filter state; "
        "skipped, snapshot bounded"
    )
    COVERAGE_UNPROVEN_WARNING = (
        "Workday facet coverage cannot be proven from available evidence; "
        "snapshot kept bounded"
    )
    COVERAGE_INCOMPLETE_WARNING = (
        "Workday advertised facet counts cannot cover the capped parent "
        "total; snapshot kept bounded"
    )
    _TENANT = re.compile(r"\btenant\s*:\s*['\"]([^'\"]+)['\"]")
    _SITE = re.compile(r"\bsiteId\s*:\s*['\"]([^'\"]+)['\"]")
    # Requisition-id shapes observed on live CXS catalogs: JR/R/J/REQ prefixes
    # plus digits (JR100132, R14702, J0107014, REQ-1001) or bare digits
    # (2618439). Badge labels ("Spotlight Job", "Regular Employee") never match.
    _REQUISITION = re.compile(r"^(?:(?:JR|R|J|REQ)-?)?\d[\d\-]*$", re.IGNORECASE)
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
        warnings: list[str] = []
        page_limit = context.page_limit(self.max_pages)
        pages_remaining = page_limit

        # Root probe: page 0 doubles as cap/facet evidence (no extra wire).
        payload0, postings0, total0 = await self._fetch_jobs_page(
            context, api_url, {}, 0
        )
        pages_remaining -= 1

        if self._is_suspicious_capped_total(total0):
            return await self._scan_capped_root(
                context, api_url, site_url, payload0, postings0, total0,
                pages_remaining, warnings,
            )
        return await self._scan_uncapped_root(
            context, api_url, site_url, payload0, postings0, total0,
            page_limit, pages_remaining, warnings,
        )

    async def _scan_uncapped_root(
        self,
        context: PortalScanContext,
        api_url: str,
        site_url: str,
        payload0: dict,
        postings0: list,
        total0: int,
        page_limit: int,
        pages_remaining: int,
        warnings: list[str],
    ) -> AdapterScanResult:
        """Original full-pagination path, unchanged semantics for uncapped
        catalogs (request sequence, warnings, and closure rules preserved)."""
        parsed_jobs: list[RawJob] = []
        complete = True
        total: int | None = None

        page_index = 0
        payload, postings, raw_total = payload0, postings0, total0
        while True:
            jobs = postings
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
            offset = page_index * self.page_size
            natural_end = offset + len(jobs) >= (total or 0) or len(jobs) < self.page_size
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
            if pages_remaining <= 0:
                complete = False
                warnings.append(
                    f"Workday pagination stopped at safety cap of {page_limit} pages"
                )
                break
            page_index += 1
            offset = page_index * self.page_size
            payload, postings, raw_total = await self._fetch_jobs_page(
                context, api_url, {}, offset
            )
            pages_remaining -= 1

        if total == 0:
            warnings.append("upstream reports zero active jobs")

        return AdapterScanResult(
            jobs=tuple(parsed_jobs),
            warnings=tuple(warnings),
            is_complete_snapshot=complete,
        )

    async def _scan_capped_root(
        self,
        context: PortalScanContext,
        api_url: str,
        site_url: str,
        payload0: dict,
        postings0: list,
        total0: int,
        pages_remaining: int,
        warnings: list[str],
    ) -> AdapterScanResult:
        """Phase-B static recursive facet subdivision (all values traversed,
        JRC identity dedup, TRUE only if every branch completes)."""
        warnings.append(self.SUBDIVISION_ACTIVATED_WARNING)
        collected: dict[str, RawJob] = {}
        seen: set[tuple] = set()
        budget = [pages_remaining]
        resolved = await self._subdivide(
            context, api_url, site_url, {}, 0,
            (payload0, postings0, total0),
            budget, seen, collected, warnings,
        )
        complete = resolved and self._subdivision_coverage_proven(
            total0, payload0.get("facets")
        )
        jobs = list(collected.values())
        if len(jobs) > context.max_jobs_per_portal:
            jobs = jobs[: context.max_jobs_per_portal]
            complete = False
            warnings.append(
                "Workday pagination stopped at job cap of "
                f"{context.max_jobs_per_portal} records"
            )
        elif len(jobs) == context.max_jobs_per_portal and jobs:
            complete = False
            warnings.append(
                "Workday pagination stopped at job cap of "
                f"{context.max_jobs_per_portal} records"
            )
        if not complete and self.CAPPED_TOTAL_WARNING not in warnings:
            warnings.append(self.CAPPED_TOTAL_WARNING)
        if not complete and self.COVERAGE_UNPROVEN_WARNING not in warnings:
            warnings.append(self.COVERAGE_UNPROVEN_WARNING)
        return AdapterScanResult(
            jobs=tuple(jobs),
            warnings=tuple(warnings),
            is_complete_snapshot=complete,
        )

    async def _subdivide(
        self,
        context: PortalScanContext,
        api_url: str,
        site_url: str,
        applied: dict[str, list[str]],
        dim_index: int,
        first: tuple[dict, list, int],
        budget: list[int],
        seen: set[tuple],
        collected: dict[str, RawJob],
        warnings: list[str],
    ) -> bool:
        """Recursively partition one capped filter state. Returns True only
        if this state and every required child state completed safely."""
        key = (dim_index, tuple(sorted((facet, tuple(values)) for facet, values in applied.items())))
        if key in seen:
            warnings.append(self.DUPLICATE_BRANCH_WARNING)
            return False
        seen.add(key)
        payload, postings, total = first
        if dim_index >= len(self._SUBDIVISION_DIMENSIONS):
            leaf_jobs, _ = await self._paginate_branch(
                context, api_url, site_url, applied, first,
                budget, warnings,
            )
            self._merge(collected, leaf_jobs)
            warnings.append(self.BRANCH_UNRESOLVED_WARNING)
            return False
        dimension = self._SUBDIVISION_DIMENSIONS[dim_index]
        facet_values = self._facet_values(payload.get("facets"), dimension)
        value_ids = [value_id for value_id, _ in facet_values]
        if len(value_ids) < 2:
            # Useless dimension here — try the next one with the same
            # filters. dim_index always advances, so this terminates.
            return await self._subdivide(
                context, api_url, site_url, applied, dim_index + 1, first,
                budget, seen, collected, warnings,
            )
        counts = [count for _, count in facet_values]
        int_counts = [count for count in counts if isinstance(count, int)]
        if int_counts and len(int_counts) == len(counts) and sum(int_counts) < total:
            # Safe direction only: advertised counts that cannot cover the
            # capped parent prove incompleteness (value list truncated, jobs
            # lacking values, or counts over another universe). Overlap can
            # only inflate sums, never explain a shortfall.
            if self.COVERAGE_INCOMPLETE_WARNING not in warnings:
                warnings.append(self.COVERAGE_INCOMPLETE_WARNING)
        counts_by_id = dict(facet_values)
        all_ok = True
        for value_id in value_ids:
            child = {**applied, dimension: [value_id]}
            if budget[0] <= 0:
                warnings.append(self.SUBDIVISION_BUDGET_WARNING)
                return False
            try:
                budget[0] -= 1
                child_first = await self._fetch_jobs_page(context, api_url, child, 0)
            except Exception:
                warnings.append(self.BRANCH_FAILED_WARNING)
                all_ok = False
                continue
            child_payload, child_postings, child_total = child_first
            if self._is_suspicious_capped_total(child_total):
                child_ok = await self._subdivide(
                    context, api_url, site_url, child, dim_index + 1,
                    child_first, budget, seen, collected, warnings,
                )
            else:
                branch_jobs, child_ok = await self._paginate_branch(
                    context, api_url, site_url, child, child_first,
                    budget, warnings,
                )
                self._merge(collected, branch_jobs)
                advertised = counts_by_id.get(value_id)
                if (
                    child_ok
                    and isinstance(advertised, int)
                    and child_total != advertised
                ):
                    warnings.append(
                        f"Workday child branch total {child_total} disagrees "
                        f"with advertised facet count {advertised} for "
                        f"{dimension}={value_id}; snapshot kept bounded"
                    )
            all_ok = child_ok and all_ok
        return all_ok

    async def _fetch_jobs_page(
        self,
        context: PortalScanContext,
        api_url: str,
        applied_facets: dict[str, list[str]],
        offset: int,
    ) -> tuple[dict, list, int]:
        """One POST page under the given facet filter. Returns
        (payload, jobPostings, total); raises on transport/schema failure
        (branch callers convert that into branch failure)."""
        response = await context.fetch(
            FetchRequest(
                api_url,
                method="POST",
                allow_cache=False,
                headers={"Accept": "application/json"},
                json_body={
                    "appliedFacets": applied_facets,
                    "limit": self.page_size,
                    "offset": offset,
                    "searchText": "",
                },
            )
        )
        require_success(response)
        payload = require_mapping(response.json(), context="Workday jobs response")
        postings = require_list(payload.get("jobPostings"), context="Workday jobPostings")
        raw_total = payload.get("total")
        if not isinstance(raw_total, int) or raw_total < 0:
            raise AdapterSchemaError("Workday jobs response is missing non-negative total")
        return payload, postings, raw_total

    async def _paginate_branch(
        self,
        context: PortalScanContext,
        api_url: str,
        site_url: str,
        applied: dict[str, list[str]],
        first: tuple[dict, list, int],
        budget: list[int],
        warnings: list[str],
    ) -> tuple[list[RawJob], bool]:
        """Paginate one uncapped filter state from its prefetched first page.
        Returns (jobs, completed): partial jobs are ALWAYS returned (callers
        merge them); completed is False on budget exhaustion, empty pages,
        fetch failure, or skipped postings."""
        _, postings, total = first
        branch_jobs: list[RawJob] = []
        ok = True
        offset = 0
        current = (first[0], postings, total)
        page_index = 0
        while True:
            _, page_postings, page_total = current
            if page_total != total:
                warning = f"Workday total changed during pagination: {total} -> {page_total}"
                if warning not in warnings:
                    warnings.append(warning)
            for index, value in enumerate(page_postings):
                job = require_mapping(value, context=f"Workday jobPostings[{index}]")
                try:
                    branch_jobs.append(self._parse_job(job, site_url=site_url, index=index))
                except AdapterSchemaError as exc:
                    ok = False
                    warnings.append(f"{exc}; skipped")
            natural_end = (
                offset + len(page_postings) >= total
                or len(page_postings) < self.page_size
            )
            if natural_end:
                break
            if not page_postings:
                warnings.append(
                    f"Workday returned an empty page before total at offset {offset}"
                )
                return branch_jobs, False
            if budget[0] <= 0:
                warnings.append(self.SUBDIVISION_BUDGET_WARNING)
                return branch_jobs, False
            page_index += 1
            offset = page_index * self.page_size
            budget[0] -= 1
            try:
                current = await self._fetch_jobs_page(context, api_url, applied, offset)
            except Exception:
                warnings.append(self.BRANCH_FAILED_WARNING)
                return branch_jobs, False
        return branch_jobs, ok

    @staticmethod
    def _merge(collected: dict[str, RawJob], branch_jobs: list[RawJob] | None) -> None:
        """Union with JRC identity dedup (requisition-shape else externalPath,
        via _parse_job). First occurrence wins; overlap is expected."""
        if not branch_jobs:
            return
        for job in branch_jobs:
            collected.setdefault(job.source_job_id, job)

    @staticmethod
    def _facet_values(facets: object, dimension: str) -> list[tuple[str, int | None]]:
        """(value id, advertised count) pairs for one facetParameter.

        Order preserved, duplicates removed, blank ids dropped. Counts may
        be absent (None) — callers must treat missing counts as unproven,
        never as zero."""
        if not isinstance(facets, list):
            return []
        for facet in facets:
            if not isinstance(facet, dict):
                continue
            if facet.get("facetParameter") != dimension:
                continue
            values = facet.get("values")
            if not isinstance(values, list):
                return []
            pairs: list[tuple[str, int | None]] = []
            seen_ids: set[str] = set()
            for value in values:
                if not isinstance(value, dict):
                    continue
                value_id = value.get("id")
                if not isinstance(value_id, str) or not value_id.strip():
                    continue
                if value_id in seen_ids:
                    continue
                seen_ids.add(value_id)
                count = value.get("count")
                pairs.append((value_id, count if isinstance(count, int) else None))
            return pairs
        return []

    @classmethod
    def _subdivision_coverage_proven(cls, total: int, facets: object) -> bool:
        """Whether offline evidence proves a capped subdivision covers its
        parent universe. Currently ALWAYS False:

        - facet value lists have no exhaustiveness marker (no per-facet
          total, no truncation flag) in observed payloads;
        - jobs may lack a value in the chosen dimension (site-less-style
          records exist; no-value postings are plausible);
        - advertised counts' universe is unknown (capped set vs true set);
        - workerSubType demonstrably overlaps (Stapply's own comment), so
          no dimension gets exclusivity by default;
        - Stapply itself performs no coverage check (union-absorb only).

        Live evidence that could flip this per tenant (NOT implemented):
        repeated-query stability of value lists, zero no-value jobs on
        every branch, advertised-vs-recovered reconciliation on all
        branches, and wrap-absence proof. Until then subdivision expands
        discovery but never completes.
        """
        return False

    @classmethod
    def _is_suspicious_capped_total(cls, total: int | None) -> bool:
        """True when the canonical total sits exactly on the provider cap.

        Provider-general (no company names): a real 2000-job board
        conservatively reads as bounded — false-incomplete is safer than
        false-complete until facet subdivision exists.
        """
        return total == cls.PROVIDER_RESULT_CAP

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
            candidates = [
                value.strip()
                for value in bullets
                if isinstance(value, str) and value.strip()
            ]
            # Cohort-60 evidence: some tenants lead bulletFields with badge
            # labels ("Spotlight Job", "Regular Employee") instead of the
            # requisition id, collapsing many jobs onto one native id.
            # Requisition shapes observed live (JR/R/J + digits, pure digits)
            # win over badge text; anything else falls back to the stable
            # externalPath rather than a collision-prone label.
            requisition = next(
                (value for value in candidates if self._REQUISITION.match(value)),
                "",
            )
        source_job_id = requisition or external_path
        # Wave 2.1 parser reuse (ats-scrapers protocol knowledge): timeType is
        # the canonical employment signal, remoteType the workplace signal.
        # Stored as house raw strings (no enum mapping, per project
        # convention); identity fields above are untouched.
        return RawJob(
            source=self.name,
            source_job_id=source_job_id,
            source_url=job_url,
            apply_url=job_url,
            title=title,
            location=string_value(job.get("locationsText")),
            employment_type=string_value(job.get("timeType")) or None,
            workplace_type=string_value(job.get("remoteType")) or None,
            ats_job_id=source_job_id,
            requisition_id=requisition or None,
            raw_payload=job,
        )
