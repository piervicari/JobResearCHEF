"""Re-run current source jobs through taxonomy without any network requests."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_agent.db.migrations import create_schema
from research_agent.db.models import CanonicalJob, Portal, ScanRun, SourceJob, utc_now
from research_agent.pipeline.filter import VacancyFilter
from research_agent.pipeline.lifecycle import ProcessingSummary, process_scan_results
from research_agent.pipeline.scanner import PortalScanResult, ScanSummary
from research_agent.sources.base import PortalTarget, RawJob


def reclassify_current_jobs(
    engine: Engine,
    *,
    vacancy_filter: VacancyFilter | None = None,
    closure_missed_successful_runs: int = 2,
) -> ProcessingSummary:
    create_schema(engine)
    now = utc_now()
    with Session(engine) as session, session.begin():
        sources = session.scalars(
            select(SourceJob).where(SourceJob.is_active.is_(True)).order_by(SourceJob.id)
        ).all()
        canonical_by_id = {
            canonical.canonical_job_id: canonical
            for canonical in session.scalars(select(CanonicalJob)).all()
        }
        grouped: dict[tuple[int | None, str], list[RawJob]] = {}
        for source in sources:
            canonical = (
                canonical_by_id.get(source.canonical_job_id)
                if source.canonical_job_id
                else None
            )
            grouped.setdefault((source.portal_id, source.adapter), []).append(
                _raw_job_from_source(source, canonical)
            )
        run = ScanRun(
            source="taxonomy_reclassification",
            status="COMPLETED",
            started_at=now,
            finished_at=now,
            portal_count=len(grouped),
            success_count=len(grouped),
            failure_count=0,
            jobs_discovered=len(sources),
            pipeline_status="NOT_PROCESSED",
        )
        session.add(run)
        session.flush()
        run_id = run.id
        targets = {
            group_key: _target_for_group(session, group_key[0]) for group_key in grouped
        }

    results = tuple(
        PortalScanResult(
            target=targets[group_key],
            adapter=group_key[1],
            status="SUCCESS",
            started_at=now,
            finished_at=now,
            jobs=tuple(jobs),
            fetch_attempts=(),
            retry_count=0,
            final_http_status=None,
            response_sha256=None,
            cache_hit=True,
            complete_snapshot=False,
        )
        for group_key, jobs in grouped.items()
    )
    scan = ScanSummary(
        scan_run_id=run_id,
        status="COMPLETED",
        portal_count=len(results),
        success_count=len(results),
        failure_count=0,
        request_count=0,
        retry_count=0,
        jobs_discovered=len(sources),
        portal_results=results,
    )
    return process_scan_results(
        engine,
        scan,
        vacancy_filter=vacancy_filter,
        closure_missed_successful_runs=closure_missed_successful_runs,
    )


def _raw_job_from_source(
    source: SourceJob, canonical: CanonicalJob | None
) -> RawJob:
    raw_payload: dict[str, object] | None = None
    if source.raw_payload_json:
        try:
            loaded = json.loads(source.raw_payload_json)
            if isinstance(loaded, dict):
                raw_payload = loaded
        except json.JSONDecodeError:
            raw_payload = None
    return RawJob(
        source=source.source,
        source_job_id=source.source_job_id,
        source_url=source.source_url,
        apply_url=source.apply_url,
        title=source.raw_title,
        company=source.raw_company,
        location=source.raw_location,
        country=source.raw_country or (canonical.country if canonical else None),
        city=source.raw_city or (canonical.city if canonical else None),
        description=source.raw_description,
        posted_at=source.posted_at,
        employment_type=source.raw_employment_type
        or (canonical.employment_type if canonical else None),
        workplace_type=source.raw_workplace_type
        or (canonical.workplace_type if canonical else None),
        ats_job_id=source.ats_job_id,
        requisition_id=source.requisition_id,
        raw_payload=raw_payload,
    )


def _target_for_group(session: Session, portal_id: int | None) -> PortalTarget:
    if portal_id is None:
        return PortalTarget(
            portal_id=None,
            jobs_search_url="manual://reclassification",
            normalized_jobs_url="manual://reclassification",
            host="local-reclassification",
            ats_families=("External source",),
            ats_confidences=("Existing provenance",),
        )
    portal = session.get(Portal, portal_id)
    if portal is None:
        raise ValueError(f"Source job references missing portal {portal_id}")
    return PortalTarget(
        portal_id=portal.id,
        jobs_search_url=portal.jobs_search_url,
        normalized_jobs_url=portal.normalized_jobs_url,
        host=portal.host,
        ats_families=tuple(json.loads(portal.ats_families_json)),
        ats_confidences=tuple(json.loads(portal.ats_confidences_json)),
    )
