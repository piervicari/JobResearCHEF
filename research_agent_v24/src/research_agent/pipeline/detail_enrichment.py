"""Selective official detail-page enrichment for AI-relevant discoveries.

The listing/search scan remains deliberately cheap.  Only jobs already classified CYBER or
NEEDS_MORE_DETAIL and lacking a useful description are eligible for this second-stage fetch.
The first implementation is intentionally restricted to the conservative ``official_html``
fallback, where the source URL is an official same-host job page and robots.txt was already
part of the listing scan contract.
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
from urllib.parse import urlsplit, urlunsplit

from selectolax.parser import HTMLParser
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_agent.config import ScannerSettings
from research_agent.db.migrations import create_schema
from research_agent.db.models import Portal, SourceJob
from research_agent.pipeline.cache import FileResponseCache
from research_agent.pipeline.http import FetchRequest, HttpFetcher


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


# Adapters whose second-stage detail page is a same-host public apply URL
# (Workday's `/apply` returns a JSON-LD JobPosting even though the listing
# is a JS-rendered SPA). The pattern is: source_url + "/apply" must still
# resolve on the same host as the portal.
_DETAIL_ADAPTERS = ("official_html", "workday")


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
        # Compute the actual detail request URL for this adapter.
        request_url = _collapse_apply_path(_detail_request_url(url, row.adapter))
        parsed_source = urlsplit(request_url)
        if parsed_source.scheme not in {"http", "https"} or not parsed_source.hostname:
            continue
        if parsed_source.hostname.casefold() != portal.host.casefold():
            # The first conservative implementation never follows a generic anchor onto a
            # third-party host. Structured ATS detail enrichment is a separate future adapter.
            continue
        host_key = portal.host.casefold()
        if host_counts.get(host_key, 0) >= max_jobs_per_host:
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
                host=portal.host,
                description_chars=len(effective_description),
            )
        )
        host_counts[host_key] = host_counts.get(host_key, 0) + 1
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
    """Fetch a tiny bounded set of same-host official job pages and requeue changed jobs."""

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
