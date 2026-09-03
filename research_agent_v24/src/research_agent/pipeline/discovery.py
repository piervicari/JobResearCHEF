"""Persist network discoveries without making semantic job decisions.

This is the V2 bridge between official-portal scanning and the future JobAnalyzer.
Every discovered source job is stored durably as ``PENDING_AI`` (or keeps its prior
AI state when unchanged). No title/description/seniority keyword filter is involved.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_agent.company.clustering import PortalClusterResolver
from research_agent.db.migrations import create_schema
from research_agent.db.models import CorporateCluster, JobObservation, ScanRun, SourceJob
from research_agent.pipeline.dedup import canonical_application_url
from research_agent.pipeline.lifecycle import _update_missing_and_closed_jobs
from research_agent.pipeline.payload import serialize_observation_payload
from research_agent.pipeline.scanner import ScanSummary
from research_agent.pipeline.source_identity import (
    source_identity_conflicts,
    variant_source_job_id,
)
from research_agent.sources.base import RawJob


@dataclass(frozen=True)
class DiscoveryPersistenceSummary:
    scan_run_id: int
    observations: int
    new_source_jobs: int
    updated_source_jobs: int
    unchanged_source_jobs: int
    duplicate_observations: int
    source_id_collisions_preserved: int
    pending_ai: int
    closed_source_jobs: int
    closed_canonical_jobs: int
    unresolved_cluster_jobs: int
    empty_portal_anomalies: int


def persist_scan_discoveries(
    engine: Engine,
    scan: ScanSummary,
    *,
    closure_missed_successful_runs: int = 2,
) -> DiscoveryPersistenceSummary:
    """Persist raw discoveries and lifecycle state, but do not classify/promote jobs."""

    if closure_missed_successful_runs < 2:
        raise ValueError("closure_missed_successful_runs must be at least 2")
    create_schema(engine)

    with Session(engine) as session, session.begin():
        run = session.get(ScanRun, scan.scan_run_id)
        if run is None:
            raise ValueError(f"Unknown scan run {scan.scan_run_id}")
        if run.pipeline_status not in {"NOT_PROCESSED", ""}:
            raise ValueError(
                f"Scan run {scan.scan_run_id} already has pipeline status "
                f"{run.pipeline_status!r}"
            )

        resolver = PortalClusterResolver(session)
        existing_sources = {
            (row.source, row.source_job_id): row
            for row in session.scalars(select(SourceJob)).all()
        }
        observed_ids_by_portal: dict[int, set[int]] = {}
        processed_keys: set[tuple[str, str]] = set()

        observations = 0
        new_source_jobs = 0
        updated_source_jobs = 0
        unchanged_source_jobs = 0
        duplicate_observations = 0
        source_id_collisions = 0
        unresolved_clusters = 0

        for portal_result in scan.portal_results:
            if portal_result.status != "SUCCESS":
                continue
            portal_id = portal_result.target.portal_id
            if portal_id is not None:
                observed_ids_by_portal.setdefault(portal_id, set())

            for raw_job in portal_result.jobs:
                resolution = (
                    resolver.resolve(portal_id=portal_id, raw_company=raw_job.company)
                    if portal_id is not None
                    else resolver.resolve_company(raw_job.company)
                )
                if resolution.corporate_cluster_id is None:
                    unresolved_clusters += 1

                storage_id, collided = _resolve_storage_source_id(
                    raw_job, existing_sources
                )
                source_key = (raw_job.source, storage_id)
                if source_key in processed_keys:
                    duplicate_observations += 1
                    continue
                processed_keys.add(source_key)
                source_id_collisions += int(collided)

                company_name = resolver.display_company_name(
                    portal_id=portal_id,
                    raw_company=raw_job.company,
                    resolution=resolution,
                )
                payload_json, payload_sha = serialize_observation_payload(
                    raw_job,
                    company_id=resolution.corporate_cluster_id,
                    company_name=company_name,
                    adapter=portal_result.adapter,
                )
                source = existing_sources.get(source_key)
                changed = source is None or source.payload_sha256 != payload_sha
                now = portal_result.finished_at

                if source is None:
                    source = SourceJob(
                        scan_run_id=scan.scan_run_id,
                        portal_id=portal_id,
                        canonical_job_id=None,
                        source=raw_job.source,
                        source_job_id=storage_id,
                        native_source_job_id=raw_job.source_job_id,
                        source_url=raw_job.source_url,
                        apply_url=raw_job.apply_url,
                        canonical_apply_url=canonical_application_url(raw_job.apply_url),
                        ats_job_id=raw_job.ats_job_id,
                        requisition_id=raw_job.requisition_id,
                        raw_title=raw_job.title,
                        raw_company=raw_job.company,
                        resolved_corporate_cluster_id=resolution.corporate_cluster_id or "",
                        resolved_company_name=company_name,
                        raw_location=raw_job.location,
                        raw_country=raw_job.country or "",
                        raw_city=raw_job.city or "",
                        raw_employment_type=raw_job.employment_type or "",
                        raw_workplace_type=raw_job.workplace_type or "",
                        raw_description=raw_job.description,
                        posted_at=raw_job.posted_at,
                        fetched_at=now,
                        adapter=portal_result.adapter,
                        parser_version="0.2.0",
                        payload_sha256=payload_sha,
                        raw_payload_json=payload_json,
                        first_seen_at=now,
                        last_seen_at=now,
                        is_active=True,
                        missing_successful_scans=0,
                        ai_status="PENDING_AI",
                        ai_attempts=0,
                    )
                    session.add(source)
                    session.flush()
                    existing_sources[source_key] = source
                    new_source_jobs += 1
                else:
                    _update_source_discovery(
                        source,
                        raw_job,
                        company_name=company_name,
                        corporate_cluster_id=resolution.corporate_cluster_id,
                        portal_id=portal_id,
                        scan_run_id=scan.scan_run_id,
                        adapter=portal_result.adapter,
                        payload_sha=payload_sha,
                        payload_json=payload_json,
                        observed_at=now,
                        content_changed=changed,
                    )
                    if changed:
                        updated_source_jobs += 1
                    else:
                        unchanged_source_jobs += 1

                if portal_id is not None:
                    observed_ids_by_portal[portal_id].add(source.id)

                session.add(
                    JobObservation(
                        source_job_row_id=source.id,
                        scan_run_id=scan.scan_run_id,
                        observed_at=now,
                        payload_sha256=payload_sha,
                        payload_changed=changed,
                        raw_payload_json=(payload_json if changed else None),
                        filter_status=source.ai_status,
                        filter_decision_json=json.dumps(
                            {
                                "decision_system": "V2_PENDING_AI",
                                "semantic_filter_applied": False,
                            },
                            separators=(",", ":"),
                            sort_keys=True,
                        ),
                        cluster_resolution_json=json.dumps(
                            asdict(resolution),
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                    )
                )
                observations += 1

        lifecycle = _update_missing_and_closed_jobs(
            session,
            scan,
            observed_ids_by_portal,
            closure_missed_successful_runs=closure_missed_successful_runs,
            additional_canonical_ids=set(),
        )

        run.new_jobs = new_source_jobs
        run.updated_jobs = updated_source_jobs
        run.duplicates = duplicate_observations
        run.jobs_closed = lifecycle.closed_source_jobs
        run.pipeline_status = "DISCOVERY_PERSISTED"

        # Count only after flushing changes; this is informational and inexpensive for local SQLite.
        session.flush()
        pending_count = len(
            session.scalars(select(SourceJob.id).where(SourceJob.ai_status == "PENDING_AI")).all()
        )

        return DiscoveryPersistenceSummary(
            scan_run_id=scan.scan_run_id,
            observations=observations,
            new_source_jobs=new_source_jobs,
            updated_source_jobs=updated_source_jobs,
            unchanged_source_jobs=unchanged_source_jobs,
            duplicate_observations=duplicate_observations,
            source_id_collisions_preserved=source_id_collisions,
            pending_ai=pending_count,
            closed_source_jobs=lifecycle.closed_source_jobs,
            closed_canonical_jobs=lifecycle.closed_canonical_jobs,
            unresolved_cluster_jobs=unresolved_clusters,
            empty_portal_anomalies=lifecycle.empty_portal_anomalies,
        )


def _resolve_storage_source_id(
    raw_job: RawJob,
    existing_sources: dict[tuple[str, str], SourceJob],
) -> tuple[str, bool]:
    native = raw_job.source_job_id.strip()
    if not native:
        return variant_source_job_id(raw_job), True

    base_key = (raw_job.source, native)
    base = existing_sources.get(base_key)
    if base is None:
        return native, False
    if not source_identity_conflicts(
        existing_title=base.raw_title,
        existing_location=base.raw_location,
        existing_apply_url=base.apply_url,
        incoming=raw_job,
    ):
        return native, False

    variant = variant_source_job_id(raw_job)
    return variant, True


def _update_source_discovery(
    source: SourceJob,
    raw_job: RawJob,
    *,
    company_name: str,
    corporate_cluster_id: str | None,
    portal_id: int | None,
    scan_run_id: int,
    adapter: str,
    payload_sha: str,
    payload_json: str,
    observed_at,
    content_changed: bool,
) -> None:
    source.scan_run_id = scan_run_id
    source.portal_id = portal_id
    source.native_source_job_id = raw_job.source_job_id
    source.source_url = raw_job.source_url
    source.apply_url = raw_job.apply_url
    source.canonical_apply_url = canonical_application_url(raw_job.apply_url)
    source.ats_job_id = raw_job.ats_job_id
    source.requisition_id = raw_job.requisition_id
    source.raw_title = raw_job.title
    source.raw_company = raw_job.company
    source.resolved_corporate_cluster_id = corporate_cluster_id or ""
    source.resolved_company_name = company_name
    source.raw_location = raw_job.location
    source.raw_country = raw_job.country or ""
    source.raw_city = raw_job.city or ""
    source.raw_employment_type = raw_job.employment_type or ""
    source.raw_workplace_type = raw_job.workplace_type or ""
    source.raw_description = raw_job.description
    source.posted_at = raw_job.posted_at
    source.fetched_at = observed_at
    source.adapter = adapter
    source.parser_version = "0.2.0"
    source.payload_sha256 = payload_sha
    source.raw_payload_json = payload_json
    source.last_seen_at = observed_at
    source.is_active = True
    source.closed_at = None
    source.missing_successful_scans = 0
    if content_changed:
        source.ai_status = "PENDING_AI"
        source.ai_last_error = None
