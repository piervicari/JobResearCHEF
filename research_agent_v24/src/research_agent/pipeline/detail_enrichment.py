"""Selective official detail-page enrichment for AI-relevant discoveries.

The listing/search scan remains deliberately cheap.  Only jobs already classified CYBER or
NEEDS_MORE_DETAIL and lacking a useful description are eligible for this second-stage fetch.
Two detail kinds exist:

* ``official_html`` — the conservative same-host public job page (robots.txt gated).
* structured ATS JSON (``workday``, ``smartrecruiters``, ``oracle``,
  ``declarative``) — one deterministic API request rendered from the stored
  catalog row, parsed with a small per-ATS parser (Wave 2 external protocol
  knowledge: Workday CXS detail, SmartRecruiters ``jobAd.sections``, Oracle
  ById detail, Eightfold ``position_details`` via the SourceSpec detail
  block). No robots check (APIs, not pages); the same HttpFetcher budgets,
  pacing, and abort semantics apply. Catalog scans never fetch details.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import urllib.robotparser
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

from selectolax.parser import HTMLParser
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_agent.config import ScannerSettings
from research_agent.db.migrations import create_schema
from research_agent.db.models import Portal, SourceJob
from research_agent.pipeline.cache import FileResponseCache
from research_agent.pipeline.http import (
    AccessChallengeError,
    FetchRequest,
    HostCircuitOpenError,
    HttpFetcher,
    RequestBudgetExceededError,
)


@dataclass(frozen=True)
class DetailCandidate:
    job_id: int
    portal_id: int
    company: str
    title: str
    ai_status: str
    source_url: str
    request_url: str
    host: str
    description_chars: int
    adapter: str = ""
    structured: bool = False
    source_name: str = ""
    # Full rendered request for declarative rows (SourceSpec-owned method /
    # URL / headers / query / body via the Phase-1 bridge). Other adapters
    # build a plain JSON GET from request_url at fetch time.
    fetch_request: FetchRequest | None = None


@dataclass(frozen=True)
class ParsedDetail:
    title: str = ""
    location: str = ""
    country: str = ""
    city: str = ""
    employment_type: str = ""
    workplace_type: str = ""
    description: str = ""
    detail_url: str = ""
    parser: str = ""


@dataclass(frozen=True)
class DetailEnrichmentSummary:
    selected_jobs: int
    requests: int
    fetched_jobs: int
    updated_jobs: int
    unchanged_jobs: int
    failed_jobs: int
    pending_ai_after: int


# Adapters eligible for second-stage detail hydration. ``official_html`` uses
# the same-host public page; the rest render one deterministic structured-API
# request from the stored catalog row (see _STRUCTURED_RENDERERS). Adapters
# not listed here (workable, teamtailor, greenhouse, lever, ashby, ...) carry
# inline-complete catalog descriptions and are never detail candidates.
_DETAIL_ADAPTERS = ("official_html", "workday", "smartrecruiters", "oracle", "declarative")

# Structured detail renderers: adapter name -> render function. Each takes a
# _StructuredRow snapshot and returns the FetchRequest to send, or None when
# the stored row cannot yield an exact detail URL (then the job is skipped,
# never guessed). One request per job, sequential, via the shared HttpFetcher.
_STRUCTURED_ADAPTERS = ("workday", "smartrecruiters", "oracle", "declarative")

# SmartRecruiters serves its public API on a dedicated first-party host while
# portals live on other hosts; a SourceSpec may likewise declare an explicit
# detail host (e.g. Microsoft → microsoft.eightfold.ai). Both are sanctioned
# cross-host cases (see selection below); everything else must stay same-host.
_SMARTRECRUITERS_API_HOST = "api.smartrecruiters.com"


@dataclass(frozen=True)
class _StructuredRow:
    adapter: str
    source_name: str
    source_url: str
    portal_host: str
    portal_jobs_url: str
    native_id: str
    ats_id: str
    raw_payload: dict


def _row_payload(raw_json: str | None) -> dict:
    if not raw_json:
        return {}
    try:
        payload = json.loads(raw_json)
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _render_workday_detail(row: _StructuredRow) -> FetchRequest | None:
    """Render GET {origin}/wday/cxs/{tenant}/{site}{externalPath} (Wave 2 evidence)."""
    parsed = urlsplit(row.source_url or "")
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    host = parsed.hostname.casefold()
    if host != row.portal_host.casefold():
        return None
    tenant = host.split(".")[0]
    segments = [part for part in parsed.path.split("/") if part]
    if not segments:
        return None
    site = segments[0]
    external_path = row.raw_payload.get("externalPath")
    if not isinstance(external_path, str) or not external_path.strip():
        idx = (row.source_url or "").find("/job/")
        if idx < 0:
            return None
        external_path = (row.source_url or "")[idx:]
    external_path = external_path.strip()
    if not external_path.startswith("/"):
        external_path = "/" + external_path
    url = (
        f"{parsed.scheme}://{parsed.hostname}/wday/cxs/"
        f"{quote(tenant, safe='')}/{quote(site, safe='')}{external_path}"
    )
    return FetchRequest(url, headers={"Accept": "application/json"})


def _render_smartrecruiters_detail(row: _StructuredRow) -> FetchRequest | None:
    """Render GET api.smartrecruiters.com/v1/companies/{slug}/postings/{id}."""
    posting_id = row.ats_id or row.native_id
    if not posting_id:
        return None
    path_parts = [
        part for part in urlsplit(row.portal_jobs_url or "").path.split("/") if part
    ]
    if not path_parts:
        return None
    company = path_parts[0]
    url = (
        f"https://{_SMARTRECRUITERS_API_HOST}/v1/companies/"
        f"{quote(company, safe='')}/postings/{quote(posting_id, safe='')}"
    )
    return FetchRequest(url, headers={"Accept": "application/json"})


def _render_oracle_detail(row: _StructuredRow) -> FetchRequest | None:
    """Render GET .../recruitingCEJobRequisitionDetails?finder=ById;Id= (Wave 2)."""
    source_id = row.ats_id or row.native_id
    if not source_id:
        return None
    parsed = urlsplit(row.source_url or "")
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    if parsed.hostname.casefold() != row.portal_host.casefold():
        return None
    origin = urlunsplit((parsed.scheme, parsed.hostname, "", "", ""))
    url = (
        f"{origin}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"
        f"?finder=ById;Id={quote(source_id, safe='')}&onlyData=true"
    )
    return FetchRequest(url, headers={"Accept": "application/json"})


_SPEC_CACHE: dict[str, dict] = {}
_BINDINGS_CACHE: dict[str, str] = {}
_BINDINGS_LOADED = False


def _bound_spec_company(portal_jobs_url: str) -> str:
    """Company id the operator bound to this exact portal URL, or ''.

    Reads the frozen declarative bindings (exact portal-URL match, same
    rule as DeclarativeSourceAdapter.supports). A declarative detail row is
    only usable when its source company equals this binding: otherwise the
    row is inconsistent and contributes no candidate (0 wire).
    """
    global _BINDINGS_LOADED
    if not _BINDINGS_LOADED:
        path = (
            Path(__file__).resolve().parent.parent
            / "sources" / "declarative" / "bindings.json"
        )
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        entries = data.get("bindings") if isinstance(data, dict) else []
        if isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                url = entry.get("normalized_jobs_url")
                spec_path = entry.get("spec_path") or entry.get("spec")
                if isinstance(url, str) and isinstance(spec_path, str):
                    stem = spec_path.rsplit("/", 1)[-1]
                    if stem.endswith(".json"):
                        _BINDINGS_CACHE[url] = stem[:-5]
        _BINDINGS_LOADED = True
    return _BINDINGS_CACHE.get(portal_jobs_url or "", "")


def _load_declarative_spec(company_id: str) -> dict | None:
    """Load the frozen v0.1 SourceSpec for one declarative company id."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", company_id or ""):
        return None
    if company_id in _SPEC_CACHE:
        return _SPEC_CACHE[company_id]
    path = (
        Path(__file__).resolve().parent.parent
        / "sources" / "declarative" / "specs" / f"{company_id}.json"
    )
    if not path.is_file():
        return None
    try:
        spec = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    if not isinstance(spec, dict):
        return None
    _SPEC_CACHE[company_id] = spec
    return spec


def _spec_detail_host(row: _StructuredRow) -> str:
    """Explicit detail host from the bound SourceSpec, or ''.

    The ONLY sanctioned cross-host source: the spec's own declared detail
    URL for this exact company. Anything else stays same-host-only.
    """
    marker = "declarative:"
    company = (
        row.source_name[len(marker):]
        if row.source_name.startswith(marker)
        else ""
    )
    spec = _load_declarative_spec(company)
    if spec is None:
        return ""
    url = (spec.get("detail") or {}).get("url") or ""
    return (urlsplit(url).hostname or "").casefold()


def _render_declarative_detail(row: _StructuredRow) -> FetchRequest | None:
    """Render the full SourceSpec detail request (Eightfold position_details).

    The bound SourceSpec owns method/URL/headers/query/body: the rendered
    dict goes through the existing Phase-1 bridge (`to_fetch_request`), so
    nothing is reconstructed or dropped. Cross-host is sanctioned ONLY by
    the spec's own explicit detail URL host (e.g. Microsoft portal
    careers.microsoft.com → microsoft.eightfold.ai); any other host,
    redirect target, or payload-inferred URL is rejected here, before HTTP.
    """
    from research_agent.sources.declarative.bridge import to_fetch_request
    from research_agent.sources.declarative.executor import render_detail_request

    # SourceJob.source is "declarative:<company_id>" (adapter namespace rule).
    company = ""
    marker = "declarative:"
    if row.source_name.startswith(marker):
        company = row.source_name[len(marker):]
    if not row.native_id:
        return None
    spec = _load_declarative_spec(company)
    if spec is None:
        return None
    rendered = render_detail_request(spec, row.native_id)
    if rendered is None:
        return None
    sanctioned_host = (urlsplit(rendered["url"]).hostname or "").casefold()
    if not sanctioned_host:
        return None
    # No host decision here: selection allows exactly {portal host, this
    # spec-declared detail host}. The URL below is byte-identical to the
    # bound SourceSpec declaration — never a redirect, payload URL, or guess.
    return to_fetch_request(rendered)


_STRUCTURED_RENDERERS = {
    "workday": _render_workday_detail,
    "smartrecruiters": _render_smartrecruiters_detail,
    "oracle": _render_oracle_detail,
    "declarative": _render_declarative_detail,
}


def _join_sections(*parts: str) -> str:
    """Deterministic semantic join: strip HTML, drop empties and exact
    normalized duplicates, keep first-seen order (B12, no provider hacks)."""
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        text = _strip_html_text(part or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return "\n\n".join(out)


def _parse_workday_detail(payload: dict, final_url: str) -> ParsedDetail:
    """Parse GET {cxs}{externalPath} → jobPostingInfo (Wave 2 evidence)."""
    info = payload.get("jobPostingInfo")
    info_dict: dict = info if isinstance(info, dict) else {}
    info = info_dict
    description = ""
    for key in ("jobDescription", "externalJobDescription", "description"):
        value = info.get(key)
        if isinstance(value, str) and value.strip():
            description = _strip_html_text(value)
            break
    location = ""
    primary = info.get("location")
    additional = info.get("additionalLocations") or []
    locs: list[str] = []
    if isinstance(primary, str) and primary.strip():
        locs.append(primary.strip())
    if isinstance(additional, list):
        for value in additional:
            if isinstance(value, str) and value.strip() and value.strip() not in locs:
                locs.append(value.strip())
    if locs:
        location = " | ".join(locs)
    return ParsedDetail(
        location=location,
        employment_type=(
            info.get("timeType") if isinstance(info.get("timeType"), str) else ""
        ),
        workplace_type=(
            info.get("remoteType") if isinstance(info.get("remoteType"), str) else ""
        ),
        description=description,
        detail_url=final_url,
        parser="workday_cxs_detail",
    )


def _parse_smartrecruiters_detail(payload: dict, final_url: str) -> ParsedDetail:
    """Parse GET .../postings/{id} → jobAd.sections (Wave 2 order)."""
    sections = (payload.get("jobAd") or {}).get("sections") or {}
    if not isinstance(sections, dict):
        sections = {}
    parts: list[str] = []
    for key in (
        "jobDescription",
        "qualifications",
        "additionalInformation",
        "companyDescription",
    ):
        section = sections.get(key)
        if isinstance(section, dict):
            text = section.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text)
    location = payload.get("location") or {}
    loc = ""
    if isinstance(location, dict):
        loc = ", ".join(
            part for part in (
                location.get("city"), location.get("region"), location.get("country"),
            ) if isinstance(part, str) and part.strip()
        )
    return ParsedDetail(
        location=loc,
        description=_join_sections(*parts),
        detail_url=final_url,
        parser="smartrecruiters_posting_detail",
    )


def _parse_oracle_detail(payload: dict, final_url: str) -> ParsedDetail:
    """Parse GET ...Details?finder=ById;Id= → External* sections (Wave 2)."""
    items = payload.get("items") or []
    detail: dict = items[0] if items and isinstance(items[0], dict) else {}
    parts: list[str] = []
    for key in (
        "ExternalDescriptionStr",
        "ExternalResponsibilitiesStr",
        "ExternalQualificationsStr",
    ):
        value = detail.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value)
    employment = ""
    for key in ("WorkerType", "JobType", "ContractType", "JobSchedule"):
        value = detail.get(key)
        if isinstance(value, str) and value.strip():
            employment = value.strip()
            break
    department = ""
    for key in ("Department", "Organization", "BusinessUnit"):
        value = detail.get(key)
        if isinstance(value, str) and value.strip():
            department = value.strip()
            break
    _ = department  # preserved in raw catalog payload; no house field (B11)
    return ParsedDetail(
        location=detail.get("PrimaryLocation") if isinstance(detail.get("PrimaryLocation"), str) else "",
        employment_type=employment,
        description=_join_sections(*parts),
        detail_url=final_url,
        parser="oracle_byid_detail",
    )


def _parse_declarative_detail(payload: dict, final_url: str, spec: dict) -> ParsedDetail:
    """Parse Eightfold position_details via the SourceSpec detail block.

    Extraction paths are evaluated on the FULL response root, exactly as
    declared (e.g. Microsoft "data.jobDescription", NVIDIA
    "data.jobDescription"). No provider branches, no unwrapping.
    """
    from research_agent.sources.declarative.executor import merge_detail_into_job

    merged = merge_detail_into_job(spec, {}, payload)
    description = _join_sections(
        merged.get("description") or "", merged.get("qualifications") or ""
    )
    return ParsedDetail(
        description=description,
        detail_url=final_url,
        parser="declarative_spec_detail",
    )


_STRUCTURED_PARSERS = {
    "workday": lambda payload, final_url, spec: _parse_workday_detail(payload, final_url),
    "smartrecruiters": lambda payload, final_url, spec: _parse_smartrecruiters_detail(payload, final_url),
    "oracle": lambda payload, final_url, spec: _parse_oracle_detail(payload, final_url),
    "declarative": lambda payload, final_url, spec: _parse_declarative_detail(payload, final_url, spec),
}


def _detail_request_url(source_url: str, adapter: str) -> str:
    """Return the URL the detail fetcher should hit.

    For `official_html` and `workday` we use the canonical public detail
    page. Workday exposes the description only on `/apply`; appending a
    second `/apply` to a URL that already ends in `/apply` is a no-op
    because the path is collapsed before the request.
    """
    base = source_url.rstrip("/")
    if adapter == "workday":
        if base.endswith("/apply"):
            return base
        return base + "/apply"
    return base


def _collapse_apply_path(path: str) -> str:
    """Ensure the URL has exactly one trailing `/apply` segment, even if
    the source URL already ended with one (defensive against double-slash
    artefacts and chained transformations)."""
    if not path:
        return path
    suffix = "/apply"
    while path.endswith(suffix + suffix):
        path = path[: -len(suffix)]
    return path


def select_detail_candidates(
    engine: Engine,
    *,
    limit: int = 5,
    min_description_chars: int = 500,
    max_jobs_per_host: int = 2,
    portal_ids: set[int] | None = None,
) -> list[DetailCandidate]:
    if limit < 1:
        raise ValueError("limit must be >= 1")
    if max_jobs_per_host < 1:
        raise ValueError("max_jobs_per_host must be >= 1")
    create_schema(engine)
    with Session(engine) as session:
        statement = (
            select(SourceJob)
            .where(
                SourceJob.is_active.is_(True),
                SourceJob.adapter.in_(_DETAIL_ADAPTERS),
                SourceJob.ai_status.in_(("CYBER", "NEEDS_MORE_DETAIL")),
            )
            .order_by(SourceJob.id)
        )
        if portal_ids is not None:
            if not portal_ids:
                return []
            statement = statement.where(SourceJob.portal_id.in_(portal_ids))
        rows = session.scalars(statement).all()
        portal_ids_for_lookup = {row.portal_id for row in rows if row.portal_id}
        portals = {
            portal.id: portal
            for portal in session.scalars(
                select(Portal).where(Portal.id.in_(portal_ids_for_lookup))
            ).all()
        }

    candidates: list[DetailCandidate] = []
    # Cyber rows are enriched first: classification may already be obvious from the title, but
    # the full description is still required for skills/experience reverse engineering.
    priority = {"CYBER": 0, "NEEDS_MORE_DETAIL": 1}
    rows = sorted(rows, key=lambda row: (priority.get(row.ai_status, 9), row.id))
    host_counts: dict[str, int] = {}
    for row in rows:
        effective_description = row.detail_description or row.raw_description
        if len(effective_description.strip()) >= min_description_chars:
            continue
        if row.portal_id is None or row.portal_id not in portals:
            continue
        portal = portals[row.portal_id]
        url = row.source_url or row.apply_url
        if not url:
            continue
        # Structured ATS detail: render one exact API request from the stored
        # catalog row. Unrenderable rows are skipped, never guessed.
        if row.adapter in _STRUCTURED_ADAPTERS:
            structured_row = _StructuredRow(
                adapter=row.adapter,
                source_name=row.source or "",
                source_url=url,
                portal_host=portal.host,
                portal_jobs_url=portal.normalized_jobs_url,
                native_id=row.native_source_job_id or "",
                ats_id=row.ats_job_id or "",
                raw_payload=_row_payload(row.raw_payload_json),
            )
            renderer = _STRUCTURED_RENDERERS[row.adapter]
            if row.adapter == "declarative":
                # Binding check: the row's source company must equal the
                # company the operator bound to this exact portal URL.
                # Otherwise the row is inconsistent (e.g. wrong portal) and
                # yields no candidate however trustworthy the spec looks.
                marker = "declarative:"
                company = (
                    row.source[len(marker):]
                    if (row.source or "").startswith(marker)
                    else ""
                )
                if not company or company != _bound_spec_company(portal.normalized_jobs_url):
                    continue
            structured_request = renderer(structured_row)
            if structured_request is None:
                continue
            request_host = urlsplit(structured_request.url).hostname or ""
            allowed_hosts = {portal.host.casefold()}
            if row.adapter == "smartrecruiters":
                allowed_hosts.add(_SMARTRECRUITERS_API_HOST)
            if row.adapter == "declarative":
                # Sanctioned cross-host ONLY from the bound SourceSpec's
                # explicit detail URL (e.g. Microsoft → microsoft.eightfold.ai).
                spec_host = _spec_detail_host(structured_row)
                if spec_host:
                    allowed_hosts.add(spec_host)
            if request_host.casefold() not in allowed_hosts:
                continue
            request_url = structured_request.url
            structured = True
            fetch_request = (
                structured_request if row.adapter == "declarative" else None
            )
        else:
            # Compute the actual detail request URL for this adapter.
            request_url = _collapse_apply_path(_detail_request_url(url, row.adapter))
            parsed_source = urlsplit(request_url)
            if parsed_source.scheme not in {"http", "https"} or not parsed_source.hostname:
                continue
            if parsed_source.hostname.casefold() != portal.host.casefold():
                # The first conservative implementation never follows a generic anchor onto a
                # third-party host. Structured ATS detail enrichment is a separate future adapter.
                continue
            structured = False
            fetch_request = None
        # max_jobs_per_host caps the host that ACTUALLY receives the HTTP
        # detail request — the CLI promises "detail pages fetched from one
        # host", and HttpFetcher budgets that same actual host. Sanctioned
        # cross-host requests (SmartRecruiters API, SourceSpec-declared
        # detail hosts such as microsoft.eightfold.ai) therefore count
        # against the detail host, not the portal host. Portal/source
        # identity is untouched; only this run cap uses the actual host.
        actual_host = (urlsplit(request_url).hostname or "").casefold()
        if not actual_host:
            continue  # malformed detail URL: never hide it behind portal host
        if host_counts.get(actual_host, 0) >= max_jobs_per_host:
            continue
        candidates.append(
            DetailCandidate(
                job_id=row.id,
                portal_id=row.portal_id,
                company=row.resolved_company_name or row.raw_company,
                title=row.detail_title or row.raw_title,
                ai_status=row.ai_status,
                source_url=url,
                request_url=request_url,
                host=actual_host,
                description_chars=len(effective_description),
                adapter=row.adapter,
                structured=structured,
                source_name=row.source or "",
                fetch_request=fetch_request,
            )
        )
        host_counts[actual_host] = host_counts.get(actual_host, 0) + 1
        if len(candidates) >= limit:
            break
    return candidates


async def enrich_official_html_details(
    engine: Engine,
    scanner: ScannerSettings,
    *,
    limit: int = 5,
    min_description_chars: int = 500,
    max_jobs_per_host: int = 2,
    inter_job_wait_seconds: float = 10.0,
    cache_directory: Path | None = None,
    progress_callback=None,
    portal_ids: set[int] | None = None,
) -> DetailEnrichmentSummary:
    """Fetch a tiny bounded set of sanctioned-host detail pages and requeue changed jobs."""

    candidates = select_detail_candidates(
        engine,
        limit=limit,
        min_description_chars=min_description_chars,
        max_jobs_per_host=max_jobs_per_host,
        portal_ids=portal_ids,
    )
    if not candidates:
        return DetailEnrichmentSummary(0, 0, 0, 0, 0, 0, _pending_count(engine))

    unique_hosts = len({candidate.host for candidate in candidates})
    max_requests = len(candidates) + unique_hosts  # one robots request per host + one page/job
    fetcher = HttpFetcher(
        global_concurrency=1,
        per_domain_concurrency=1,
        per_domain_min_interval_seconds=max(10.0, scanner.per_domain_min_interval_seconds),
        request_timeout_seconds=scanner.request_timeout_seconds,
        max_retries=0,
        backoff_base_seconds=scanner.backoff_base_seconds,
        backoff_max_seconds=scanner.backoff_max_seconds,
        max_retry_after_seconds=scanner.max_retry_after_seconds,
        jitter_seconds=0.0,
        max_response_bytes=scanner.max_response_bytes,
        max_redirects=scanner.max_redirects,
        max_requests_per_host_per_run=max_requests,
        max_requests_per_run=max_requests,
        allow_private_networks=scanner.allow_private_networks,
        allow_https_to_http_redirects=scanner.allow_https_to_http_redirects,
        user_agent=scanner.resolved_user_agent,
        cache=FileResponseCache(cache_directory) if cache_directory else None,
        resolve_dns=True,
    )

    robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
    request_count = 0
    fetched = 0
    updated = 0
    unchanged = 0
    failed = 0

    async with fetcher:
        for index, candidate in enumerate(candidates, start=1):
            if progress_callback:
                progress_callback(
                    {
                        "event": "detail_start",
                        "index": index,
                        "count": len(candidates),
                        "candidate": candidate,
                    }
                )
            try:
                if candidate.structured:
                    parsed, wire_requests = await _fetch_structured_detail(fetcher, candidate)
                    request_count += wire_requests
                else:
                    # robots check is run against the actual detail URL, not the
                    # raw source URL, because that's what we will actually fetch.
                    allowed, robots_requests = await _robots_allows(
                        fetcher, candidate.request_url, robots, user_agent="research-agent-pier"
                    )
                    request_count += robots_requests
                    if not allowed:
                        raise RuntimeError("robots.txt disallows detail URL")
                    response = await fetcher.fetch(
                        FetchRequest(candidate.request_url, headers={"Accept": "text/html,*/*;q=0.8"})
                    )
                    request_count += 1
                    if not 200 <= response.status_code < 300:
                        raise RuntimeError(f"detail page returned HTTP {response.status_code}")
                    parsed = parse_detail_html(response.text, final_url=response.final_url)
                if not parsed.description.strip():
                    # B18: an empty detail must not overwrite catalog data,
                    # mark complete, or requeue AI. Record as failure.
                    raise RuntimeError("detail response carried no usable description")
                fetched += 1
                changed = _store_detail(engine, candidate.job_id, parsed)
                updated += int(changed)
                unchanged += int(not changed)
                if progress_callback:
                    progress_callback({
                        "event": "detail_result",
                        "candidate": candidate,
                        "status": "updated" if changed else "unchanged",
                        "description_chars": len(parsed.description),
                        "detail_title": parsed.title,
                        "detail_location": parsed.location,
                        "parser": parsed.parser,
                    })
            except (HostCircuitOpenError, AccessChallengeError, RequestBudgetExceededError) as exc:
                # Terminal for this host/run: 403/429/challenge/exhausted
                # budget must not hammer the same host with the next candidate.
                failed += 1
                if progress_callback:
                    progress_callback({"event": "detail_error", "candidate": candidate, "error": f"{type(exc).__name__}: {exc}"})
                break
            except Exception as exc:  # isolated by design; one detail page cannot stop the cohort
                failed += 1
                if progress_callback:
                    progress_callback({"event": "detail_error", "candidate": candidate, "error": f"{type(exc).__name__}: {exc}"})
            if index < len(candidates) and inter_job_wait_seconds > 0:
                await asyncio.sleep(inter_job_wait_seconds)

    return DetailEnrichmentSummary(
        selected_jobs=len(candidates),
        requests=request_count,
        fetched_jobs=fetched,
        updated_jobs=updated,
        unchanged_jobs=unchanged,
        failed_jobs=failed,
        pending_ai_after=_pending_count(engine),
    )


async def _fetch_structured_detail(
    fetcher: HttpFetcher, candidate: DetailCandidate
) -> tuple[ParsedDetail, int]:
    """Fetch one structured ATS detail request. Returns (parsed, wire_requests).

    Raises on any failure (B18: the caller records failure without touching
    catalog data). Spec is resolved here for declarative rows only.
    """
    parser = _STRUCTURED_PARSERS[candidate.adapter]
    spec: dict | None = None
    if candidate.adapter == "declarative":
        marker = "declarative:"
        company = (
            candidate.source_name[len(marker):]
            if candidate.source_name.startswith(marker)
            else ""
        )
        spec = _load_declarative_spec(company)
        if spec is None:
            raise RuntimeError("no declarative spec available for detail render")
    if candidate.fetch_request is not None:
        # Declarative: the exact SourceSpec-rendered request (method, URL,
        # headers, query/body) via the Phase-1 bridge — never reconstructed.
        request = candidate.fetch_request
    else:
        request = FetchRequest(
            candidate.request_url, headers={"Accept": "application/json"})
    response = await fetcher.fetch(request)
    if not 200 <= response.status_code < 300:
        raise RuntimeError(f"detail API returned HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError:
        raise RuntimeError("detail response is not JSON") from None
    if not isinstance(payload, dict):
        raise RuntimeError("detail response has an unexpected JSON shape")
    return parser(payload, response.final_url, spec), 1


async def _robots_allows(
    fetcher: HttpFetcher,
    url: str,
    cache: dict[str, urllib.robotparser.RobotFileParser | None],
    *,
    user_agent: str,
) -> tuple[bool, int]:
    parsed = urlsplit(url)
    origin = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    if origin in cache:
        parser = cache[origin]
        return (True if parser is None else parser.can_fetch(user_agent, url)), 0
    robots_url = f"{origin}/robots.txt"
    response = await fetcher.fetch(FetchRequest(robots_url, headers={"Accept": "text/plain,*/*;q=0.1"}))
    if response.status_code == 404:
        cache[origin] = None
        return True, 1
    if not 200 <= response.status_code < 300:
        raise RuntimeError(f"robots.txt returned HTTP {response.status_code}")
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(response.text.splitlines())
    cache[origin] = parser
    return parser.can_fetch(user_agent, url), 1


def parse_detail_html(html: str, *, final_url: str) -> ParsedDetail:
    document = HTMLParser(html)
    json_ld = _json_ld_detail(document)
    if json_ld is not None and len(json_ld.description.strip()) >= 20:
        return ParsedDetail(
            title=json_ld.title,
            location=json_ld.location,
            country=json_ld.country,
            city=json_ld.city,
            employment_type=json_ld.employment_type,
            workplace_type=json_ld.workplace_type,
            description=json_ld.description,
            detail_url=final_url,
            parser="json_ld_jobposting",
        )

    # Keep the useful main job content but remove obvious navigation/application boilerplate.
    for selector in ("script", "style", "noscript", "svg", "nav", "footer", "header", "form"):
        for node in document.css(selector):
            node.decompose()
    container = (
        document.css_first("main")
        or document.css_first("article")
        or document.css_first('[role="main"]')
        or document.body
    )
    if container is None:
        raise ValueError("detail page has no parseable body")
    lines = _clean_lines(container.text(separator="\n"))
    description = "\n".join(lines)
    if len(description) < 100:
        raise ValueError("detail page contains too little usable text")
    title_node = document.css_first("h1")
    title = _clean_text(title_node.text(separator=" ")) if title_node is not None else ""
    location = _label_value(lines, ("location", "locations"))
    employment = _label_value(lines, ("employment type", "job type"))
    workplace = _label_value(lines, ("remote status",))
    if not location:
        location, inferred_workplace = _dot_header_location(lines, title)
        workplace = workplace or inferred_workplace
    return ParsedDetail(
        title=title,
        location=location,
        employment_type=employment,
        workplace_type=workplace,
        description=description[:60_000],
        detail_url=final_url,
        parser="main_text",
    )


def _store_detail(engine: Engine, job_id: int, detail: ParsedDetail) -> bool:
    payload = {
        "title": detail.title,
        "location": detail.location,
        "country": detail.country,
        "city": detail.city,
        "employment_type": detail.employment_type,
        "workplace_type": detail.workplace_type,
        "description": detail.description,
        "detail_url": detail.detail_url,
        "parser": detail.parser,
    }
    payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    sha = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    with Session(engine) as session, session.begin():
        row = session.get(SourceJob, job_id)
        if row is None:
            raise RuntimeError(f"source job {job_id} disappeared")
        changed = row.detail_payload_sha256 != sha
        row.detail_title = detail.title
        row.detail_location = detail.location
        row.detail_country = detail.country
        row.detail_city = detail.city
        row.detail_employment_type = detail.employment_type
        row.detail_workplace_type = detail.workplace_type
        row.detail_description = detail.description
        row.detail_url = detail.detail_url
        row.detail_payload_sha256 = sha
        row.detail_fetched_at = datetime.now(UTC)
        if changed:
            row.ai_status = "PENDING_AI"
            row.ai_last_error = None
        return changed


def _pending_count(engine: Engine) -> int:
    with Session(engine) as session:
        return len(
            session.scalars(
                select(SourceJob.id).where(SourceJob.ai_status == "PENDING_AI", SourceJob.is_active.is_(True))
            ).all()
        )


def _json_ld_detail(document: HTMLParser) -> ParsedDetail | None:
    for node in document.css('script[type="application/ld+json"]'):
        try:
            value = json.loads(node.text())
        except Exception:
            continue
        for item in _walk_json(value):
            types = item.get("@type")
            type_values = types if isinstance(types, list) else [types]
            if not any(str(v).casefold() == "jobposting" for v in type_values):
                continue
            title = _clean_text(str(item.get("title") or ""))
            description = _strip_html_text(str(item.get("description") or ""))
            location, country, city = _json_ld_location(item)
            employment = item.get("employmentType")
            if isinstance(employment, list):
                employment_type = " | ".join(str(v) for v in employment if v)
            else:
                employment_type = _clean_text(str(employment or ""))
            workplace = "remote" if str(item.get("jobLocationType") or "").casefold() == "telecommute" else ""
            return ParsedDetail(
                title=title,
                location=location,
                country=country,
                city=city,
                employment_type=employment_type,
                workplace_type=workplace,
                description=description,
                parser="json_ld_jobposting",
            )
    return None


def _walk_json(value):
    if isinstance(value, list):
        for item in value:
            yield from _walk_json(item)
    elif isinstance(value, dict):
        graph = value.get("@graph")
        if graph is not None:
            yield from _walk_json(graph)
        yield value


def _json_ld_location(item: dict) -> tuple[str, str, str]:
    raw = item.get("jobLocation")
    locations = raw if isinstance(raw, list) else ([raw] if raw else [])
    displays: list[str] = []
    countries: list[str] = []
    cities: list[str] = []
    for loc in locations:
        if not isinstance(loc, dict):
            continue
        address = loc.get("address")
        if not isinstance(address, dict):
            continue
        city = _clean_text(str(address.get("addressLocality") or ""))
        region = _clean_text(str(address.get("addressRegion") or ""))
        country = _clean_text(str(address.get("addressCountry") or ""))
        display = ", ".join(v for v in (city, region, country) if v)
        if display:
            displays.append(display)
        if city:
            cities.append(city)
        if country:
            countries.append(country)
    return (
        " | ".join(dict.fromkeys(displays)),
        " | ".join(dict.fromkeys(countries)),
        " | ".join(dict.fromkeys(cities)),
    )


def _strip_html_text(value: str) -> str:
    if not value:
        return ""
    fragment = HTMLParser(value)
    return "\n".join(_clean_lines(fragment.text(separator="\n")))


def _clean_lines(value: str) -> list[str]:
    lines: list[str] = []
    for raw in value.splitlines():
        line = _clean_text(raw)
        if line and (not lines or lines[-1] != line):
            lines.append(line)
    return lines


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _label_value(lines: list[str], labels: tuple[str, ...]) -> str:
    lowered = [line.casefold().rstrip(":") for line in lines]
    label_set = {label.casefold() for label in labels}
    for index, line in enumerate(lowered):
        if line in label_set and index + 1 < len(lines):
            candidate = lines[index + 1]
            if len(candidate) <= 200:
                return candidate
    return ""


def _dot_header_location(lines: list[str], title: str) -> tuple[str, str]:
    # Teamtailor-style pages often expose "Department · City · Hybrid" immediately above H1.
    try:
        title_index = next(i for i, line in enumerate(lines) if title and line == title)
    except StopIteration:
        title_index = min(len(lines), 20)
    for line in reversed(lines[max(0, title_index - 5):title_index]):
        if " · " not in line:
            continue
        parts = [part.strip() for part in line.split(" · ") if part.strip()]
        if len(parts) >= 2:
            workplace = parts[-1] if parts[-1].casefold() in {"hybrid", "remote", "on-site", "onsite"} else ""
            location = parts[-2] if workplace and len(parts) >= 2 else parts[-1]
            return location, workplace
    return "", ""
