"""Persist observations, deduplicate canonical jobs and update safe lifecycle state."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_agent.company.clustering import PortalClusterResolver
from research_agent.db.migrations import create_schema
from research_agent.db.models import (
    CanonicalJob,
    JobObservation,
    Portal,
    ScanRun,
    SourceJob,
    utc_now,
)
from research_agent.filters.common import normalize_text
from research_agent.pipeline.dedup import (
    DedupCandidate,
    DedupIndex,
    canonical_application_url,
    canonical_fingerprint,
)
from research_agent.pipeline.filter import VacancyFilter, VacancyFilterResult
from research_agent.pipeline.normalizer import normalize_job
from research_agent.pipeline.payload import serialize_observation_payload
from research_agent.pipeline.scanner import ScanSummary
from research_agent.sources.base import RawJob


@dataclass(frozen=True)
class ProcessingSummary:
    scan_run_id: int
    observations: int
    included: int
    review: int
    excluded: int
    new_canonical_jobs: int
    updated_canonical_jobs: int
    duplicate_observations: int
    closed_source_jobs: int
    closed_canonical_jobs: int
    unresolved_cluster_jobs: int
    empty_portal_anomalies: int


def process_scan_results(
    engine: Engine,
    scan: ScanSummary,
    *,
    vacancy_filter: VacancyFilter | None = None,
    closure_missed_successful_runs: int = 2,
) -> ProcessingSummary:
    if closure_missed_successful_runs < 2:
        raise ValueError("closure_missed_successful_runs must be at least 2")
    create_schema(engine)
    vacancy_filter = vacancy_filter or VacancyFilter()

    with Session(engine) as session, session.begin():
        run = session.get(ScanRun, scan.scan_run_id)
        if run is None:
            raise ValueError(f"Unknown scan run {scan.scan_run_id}")
        if run.pipeline_status == "COMPLETED":
            raise ValueError(f"Scan run {scan.scan_run_id} has already been processed")
        run.config_snapshot_json = _config_snapshot_json(
            run.config_snapshot_json, vacancy_filter
        )

        resolver = PortalClusterResolver(session)
        dedup = _load_dedup_index(session)
        existing_sources = {
            (source.source, source.source_job_id): source
            for source in session.scalars(select(SourceJob)).all()
        }
        observed_ids_by_portal: dict[int, set[int]] = {}
        filter_counts = {"INCLUDE": 0, "REVIEW": 0, "EXCLUDE": 0}
        new_canonical = 0
        updated_canonical_ids: set[str] = set()
        duplicate_observations = 0
        unresolved_clusters = 0
        detached_canonical_ids: set[str] = set()
        processed_source_keys: set[tuple[str, str]] = set()

        for portal_result in scan.portal_results:
            if portal_result.status != "SUCCESS":
                continue
            portal_id = portal_result.target.portal_id
            if portal_id is not None:
                observed_ids_by_portal.setdefault(portal_id, set())
            for raw_job in portal_result.jobs:
                source_key = (raw_job.source, raw_job.source_job_id)
                if source_key in processed_source_keys:
                    duplicate_observations += 1
                    continue
                processed_source_keys.add(source_key)
                resolution = (
                    resolver.resolve(portal_id=portal_id, raw_company=raw_job.company)
                    if portal_id is not None
                    else resolver.resolve_company(raw_job.company)
                )
                if resolution.corporate_cluster_id is None:
                    unresolved_clusters += 1
                filtered = vacancy_filter.evaluate(raw_job)
                filter_counts[filtered.status] += 1
                resolved_company_name = resolver.display_company_name(
                    portal_id=portal_id,
                    raw_company=raw_job.company,
                    resolution=resolution,
                )
                raw_payload_json, payload_sha = serialize_observation_payload(
                    raw_job,
                    company_id=resolution.corporate_cluster_id,
                    company_name=resolved_company_name,
                    adapter=portal_result.adapter,
                )
                source = existing_sources.get(source_key)
                payload_changed = source is None or source.payload_sha256 != payload_sha

                canonical: CanonicalJob | None = None
                if filtered.status != "EXCLUDE":
                    dedup_candidate = _dedup_candidate(
                        raw_job,
                        portal_id=portal_id,
                        corporate_cluster_id=resolution.corporate_cluster_id,
                    )
                    match = dedup.match(dedup_candidate)
                    if match is not None:
                        canonical = session.get(CanonicalJob, match.canonical_job_id)
                    if canonical is None:
                        canonical = _new_canonical_job(
                            raw_job,
                            filtered,
                            corporate_cluster_id=resolution.corporate_cluster_id,
                            portal_id=portal_id,
                            scan_run_id=scan.scan_run_id,
                        )
                        session.add(canonical)
                        session.flush()
                        new_canonical += 1
                    else:
                        _update_canonical_job(
                            canonical,
                            raw_job,
                            filtered,
                            corporate_cluster_id=resolution.corporate_cluster_id,
                            portal_id=portal_id,
                            scan_run_id=scan.scan_run_id,
                        )
                        updated_canonical_ids.add(canonical.canonical_job_id)
                        duplicate_observations += 1
                    dedup.add(
                        DedupCandidate(
                            **{
                                **asdict(dedup_candidate),
                                "canonical_job_id": canonical.canonical_job_id,
                            }
                        )
                    )

                now = portal_result.finished_at
                if source is None:
                    source = SourceJob(
                        scan_run_id=scan.scan_run_id,
                        portal_id=portal_id,
                        canonical_job_id=(canonical.canonical_job_id if canonical else None),
                        source=raw_job.source,
                        source_job_id=raw_job.source_job_id,
                        native_source_job_id=raw_job.source_job_id,
                        source_url=raw_job.source_url,
                        apply_url=raw_job.apply_url,
                        canonical_apply_url=canonical_application_url(raw_job.apply_url),
                        ats_job_id=raw_job.ats_job_id,
                        requisition_id=raw_job.requisition_id,
                        raw_title=raw_job.title,
                        raw_company=raw_job.company,
                        resolved_corporate_cluster_id=resolution.corporate_cluster_id or "",
                        resolved_company_name=resolved_company_name,
                        raw_location=raw_job.location,
                        raw_country=raw_job.country or "",
                        raw_city=raw_job.city or "",
                        raw_employment_type=raw_job.employment_type or "",
                        raw_workplace_type=raw_job.workplace_type or "",
                        raw_description=raw_job.description,
                        posted_at=raw_job.posted_at,
                        fetched_at=now,
                        adapter=portal_result.adapter,
                        parser_version="0.1.0",
                        payload_sha256=payload_sha,
                        raw_payload_json=raw_payload_json,
                        first_seen_at=now,
                        last_seen_at=now,
                        is_active=True,
                        missing_successful_scans=0,
                    )
                    session.add(source)
                    session.flush()
                    existing_sources[source_key] = source
                else:
                    if source.canonical_job_id and canonical is None:
                        detached_canonical_ids.add(source.canonical_job_id)
                    _update_source_job(
                        source,
                        raw_job,
                        portal_id=portal_id,
                        scan_run_id=scan.scan_run_id,
                        adapter=portal_result.adapter,
                        canonical_job_id=(canonical.canonical_job_id if canonical else None),
                        resolved_corporate_cluster_id=resolution.corporate_cluster_id,
                        resolved_company_name=resolved_company_name,
                        payload_sha=payload_sha,
                        raw_payload_json=raw_payload_json,
                        observed_at=now,
                    )

                if portal_id is not None:
                    observed_ids_by_portal[portal_id].add(source.id)
                session.add(
                    JobObservation(
                        source_job_row_id=source.id,
                        scan_run_id=scan.scan_run_id,
                        observed_at=now,
                        payload_sha256=payload_sha,
                        payload_changed=payload_changed,
                        raw_payload_json=(raw_payload_json if payload_changed else None),
                        filter_status=filtered.status,
                        filter_decision_json=json.dumps(
                            asdict(filtered), ensure_ascii=False, sort_keys=True
                        ),
                        cluster_resolution_json=json.dumps(
                            asdict(resolution), ensure_ascii=False, sort_keys=True
                        ),
                    )
                )

        lifecycle = _update_missing_and_closed_jobs(
            session,
            scan,
            observed_ids_by_portal,
            closure_missed_successful_runs=closure_missed_successful_runs,
            additional_canonical_ids=detached_canonical_ids,
        )
        run.new_jobs = new_canonical
        run.updated_jobs = len(updated_canonical_ids)
        run.duplicates = duplicate_observations
        run.jobs_closed = lifecycle.closed_canonical_jobs
        run.pipeline_status = "COMPLETED"

        return ProcessingSummary(
            scan_run_id=scan.scan_run_id,
            observations=sum(filter_counts.values()),
            included=filter_counts["INCLUDE"],
            review=filter_counts["REVIEW"],
            excluded=filter_counts["EXCLUDE"],
            new_canonical_jobs=new_canonical,
            updated_canonical_jobs=len(updated_canonical_ids),
            duplicate_observations=duplicate_observations,
            closed_source_jobs=lifecycle.closed_source_jobs,
            closed_canonical_jobs=lifecycle.closed_canonical_jobs,
            unresolved_cluster_jobs=unresolved_clusters,
            empty_portal_anomalies=lifecycle.empty_portal_anomalies,
        )


@dataclass(frozen=True)
class _LifecycleCounts:
    closed_source_jobs: int
    closed_canonical_jobs: int
    empty_portal_anomalies: int


def _update_missing_and_closed_jobs(
    session: Session,
    scan: ScanSummary,
    observed_ids_by_portal: dict[int, set[int]],
    *,
    closure_missed_successful_runs: int,
    additional_canonical_ids: set[str],
) -> _LifecycleCounts:
    affected_canonical_ids = set(additional_canonical_ids)
    closed_sources = 0
    empty_anomalies = 0
    for result in scan.portal_results:
        if result.status != "SUCCESS":
            continue
        if not result.complete_snapshot:
            continue
        if result.target.portal_id is None:
            continue
        portal = session.get(Portal, result.target.portal_id)
        if portal is None:
            continue
        active_sources = session.scalars(
            select(SourceJob).where(
                SourceJob.portal_id == portal.id,
                SourceJob.is_active.is_(True),
            )
        ).all()
        observed_ids = observed_ids_by_portal.get(portal.id, set())
        if not result.jobs and active_sources:
            portal.consecutive_empty_scans += 1
            portal.health_state = "DEGRADED"
            empty_anomalies += 1
            if portal.consecutive_empty_scans < closure_missed_successful_runs:
                continue
        else:
            portal.consecutive_empty_scans = 0

        for source in active_sources:
            if source.id in observed_ids:
                continue
            source.missing_successful_scans += 1
            if source.missing_successful_scans >= closure_missed_successful_runs:
                source.is_active = False
                source.closed_at = utc_now()
                closed_sources += 1
                if source.canonical_job_id:
                    affected_canonical_ids.add(source.canonical_job_id)

    closed_canonical = 0
    for canonical_id in affected_canonical_ids:
        canonical = session.get(CanonicalJob, canonical_id)
        if canonical is None:
            continue
        active_source = session.scalar(
            select(SourceJob.id).where(
                SourceJob.canonical_job_id == canonical_id,
                SourceJob.is_active.is_(True),
            )
        )
        if active_source is None and canonical.active:
            canonical.active = False
            canonical.closed_at = utc_now()
            closed_canonical += 1
    return _LifecycleCounts(closed_sources, closed_canonical, empty_anomalies)


def _load_dedup_index(session: Session) -> DedupIndex:
    index = DedupIndex()
    rows = session.execute(
        select(SourceJob, CanonicalJob).join(
            CanonicalJob, CanonicalJob.canonical_job_id == SourceJob.canonical_job_id
        )
    ).all()
    for source, canonical in rows:
        index.add(
            DedupCandidate(
                canonical_job_id=canonical.canonical_job_id,
                source=source.source,
                source_job_id=source.source_job_id,
                apply_url=source.apply_url,
                corporate_cluster_id=(
                    canonical.corporate_cluster_id
                    or _unresolved_namespace(
                        portal_id=source.portal_id,
                        raw_company=source.raw_company,
                        source=source.source,
                    )
                ),
                title=source.raw_title,
                location=source.raw_location,
                ats_job_id=source.ats_job_id,
                requisition_id=source.requisition_id,
            )
        )
    return index


def _dedup_candidate(
    raw_job: RawJob, *, portal_id: int | None, corporate_cluster_id: str | None
) -> DedupCandidate:
    return DedupCandidate(
        canonical_job_id="",
        source=raw_job.source,
        source_job_id=raw_job.source_job_id,
        apply_url=raw_job.apply_url,
        corporate_cluster_id=corporate_cluster_id
        or _unresolved_namespace(
            portal_id=portal_id,
            raw_company=raw_job.company,
            source=raw_job.source,
        ),
        title=raw_job.title,
        location=raw_job.location,
        ats_job_id=raw_job.ats_job_id,
        requisition_id=raw_job.requisition_id,
    )


def _new_canonical_job(
    raw_job: RawJob,
    filtered: VacancyFilterResult,
    *,
    corporate_cluster_id: str | None,
    portal_id: int | None,
    scan_run_id: int,
) -> CanonicalJob:
    normalized = normalize_job(raw_job)
    cluster_key = corporate_cluster_id or _unresolved_namespace(
        portal_id=portal_id,
        raw_company=raw_job.company,
        source=raw_job.source,
    )
    now = utc_now()
    return CanonicalJob(
        canonical_job_id=f"CJ-{uuid.uuid4().hex}",
        corporate_cluster_id=corporate_cluster_id,
        canonical_fingerprint=canonical_fingerprint(
            corporate_cluster_id=cluster_key,
            title=raw_job.title,
            location=raw_job.location,
            requisition_id=raw_job.requisition_id,
        ),
        filter_status=filtered.status,
        primary_apply_url=canonical_application_url(raw_job.apply_url),
        title=normalized.title,
        normalized_title=normalized.normalized_title,
        location=normalized.location,
        country=filtered.geography.category or raw_job.country,
        city=raw_job.city,
        workplace_type=raw_job.workplace_type,
        description=normalized.description,
        employment_type=raw_job.employment_type,
        seniority=filtered.seniority.category,
        cyber_category=filtered.cyber.category,
        posted_at=raw_job.posted_at,
        first_seen_at=now,
        last_seen_at=now,
        active=True,
        last_seen_successful_run_id=scan_run_id,
    )


def _update_canonical_job(
    canonical: CanonicalJob,
    raw_job: RawJob,
    filtered: VacancyFilterResult,
    *,
    corporate_cluster_id: str | None,
    portal_id: int | None,
    scan_run_id: int,
) -> None:
    normalized = normalize_job(raw_job)
    if canonical.corporate_cluster_id is None and corporate_cluster_id is not None:
        canonical.corporate_cluster_id = corporate_cluster_id
    cluster_key = canonical.corporate_cluster_id or _unresolved_namespace(
        portal_id=portal_id,
        raw_company=raw_job.company,
        source=raw_job.source,
    )
    canonical.canonical_fingerprint = canonical_fingerprint(
        corporate_cluster_id=cluster_key,
        title=raw_job.title,
        location=raw_job.location,
        requisition_id=raw_job.requisition_id,
    )
    canonical.filter_status = filtered.status
    canonical.primary_apply_url = canonical_application_url(raw_job.apply_url)
    canonical.title = normalized.title
    canonical.normalized_title = normalized.normalized_title
    canonical.location = normalized.location
    canonical.country = filtered.geography.category or raw_job.country
    canonical.city = raw_job.city
    canonical.workplace_type = raw_job.workplace_type
    canonical.description = normalized.description
    canonical.employment_type = raw_job.employment_type
    canonical.seniority = filtered.seniority.category
    canonical.cyber_category = filtered.cyber.category
    canonical.posted_at = raw_job.posted_at or canonical.posted_at
    canonical.last_seen_at = utc_now()
    canonical.active = True
    canonical.closed_at = None
    canonical.last_seen_successful_run_id = scan_run_id


def _update_source_job(
    source: SourceJob,
    raw_job: RawJob,
    *,
    portal_id: int | None,
    scan_run_id: int,
    adapter: str,
    canonical_job_id: str | None,
    resolved_corporate_cluster_id: str | None,
    resolved_company_name: str,
    payload_sha: str,
    raw_payload_json: str,
    observed_at: datetime,
) -> None:
    source.scan_run_id = scan_run_id
    source.portal_id = portal_id
    source.canonical_job_id = canonical_job_id
    source.native_source_job_id = raw_job.source_job_id
    source.source_url = raw_job.source_url
    source.apply_url = raw_job.apply_url
    source.canonical_apply_url = canonical_application_url(raw_job.apply_url)
    source.ats_job_id = raw_job.ats_job_id
    source.requisition_id = raw_job.requisition_id
    source.raw_title = raw_job.title
    source.raw_company = raw_job.company
    source.resolved_corporate_cluster_id = resolved_corporate_cluster_id or ""
    source.resolved_company_name = resolved_company_name
    source.raw_location = raw_job.location
    source.raw_country = raw_job.country or ""
    source.raw_city = raw_job.city or ""
    source.raw_employment_type = raw_job.employment_type or ""
    source.raw_workplace_type = raw_job.workplace_type or ""
    source.raw_description = raw_job.description
    source.posted_at = raw_job.posted_at
    source.fetched_at = observed_at
    source.adapter = adapter
    source.parser_version = "0.1.0"
    source.payload_sha256 = payload_sha
    source.raw_payload_json = raw_payload_json
    source.last_seen_at = observed_at
    source.is_active = True
    source.closed_at = None
    source.missing_successful_scans = 0


def _config_snapshot_json(
    existing_json: str | None, vacancy_filter: VacancyFilter
) -> str:
    existing: object = json.loads(existing_json) if existing_json else {}
    if not isinstance(existing, dict):
        existing = {"scanner": existing}
    elif existing and "scanner" not in existing and "filter" not in existing:
        existing = {"scanner": existing}
    existing["filter"] = vacancy_filter.config_snapshot()
    return json.dumps(existing, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_default(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _unresolved_namespace(
    *, portal_id: int | None, raw_company: str, source: str
) -> str:
    if portal_id is not None:
        return f"PORTAL:{portal_id}"
    return f"EXTERNAL:{normalize_text(source)}:{normalize_text(raw_company)}"
