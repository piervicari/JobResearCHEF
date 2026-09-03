import json
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_agent.db.migrations import create_schema
from research_agent.db.models import (
    CanonicalJob,
    ClusterPortalMapping,
    CorporateCluster,
    ImportBatch,
    JobObservation,
    Portal,
    ScanRun,
    SourceJob,
)
from research_agent.pipeline.discovery import persist_scan_discoveries
from research_agent.pipeline.lifecycle import process_scan_results
from research_agent.pipeline.reclassify import reclassify_current_jobs
from research_agent.pipeline.scanner import PortalScanResult, ScanSummary
from research_agent.sources.base import PortalTarget, RawJob


def _seed_registry(engine: Engine) -> tuple[int, str]:
    create_schema(engine)
    with Session(engine) as session, session.begin():
        batch = ImportBatch(
            source_kind="test",
            source_filename="fixture.csv",
            source_path="fixture.csv",
            source_sha256="a" * 64,
            source_version="test",
            status="COMPLETED",
        )
        session.add(batch)
        session.flush()
        cluster = CorporateCluster(
            corporate_cluster_id="CG-1",
            representative_canonical_employer="Example Ltd",
            canonical_employers_json='["Example Ltd"]',
            parent_groups_json="[]",
            entity_classes_json='["Employer Candidate"]',
            eligibility_values_json='["Yes"]',
            sectors_json='["Technology"]',
            discovery_geographies_json='["Italy"]',
            org_types_json='["Company"]',
            record_count=1,
            has_primary_scan_eligibility=True,
            active_in_master=True,
            import_batch_id=batch.id,
        )
        session.add(cluster)
        portal = Portal(
            normalized_jobs_url="https://jobs.example.test/openings",
            jobs_search_url="https://jobs.example.test/openings",
            scheme="https",
            host="jobs.example.test",
            ats_families_json='["fixture"]',
            ats_confidences_json='["Verified"]',
            metadata_conflict=False,
            cluster_count=1,
            active_in_registry=True,
            health_state="UNKNOWN",
            consecutive_failures=0,
            consecutive_empty_scans=0,
            import_batch_id=batch.id,
        )
        session.add(portal)
        session.flush()
        session.add(
            ClusterPortalMapping(
                corporate_cluster_id=cluster.corporate_cluster_id,
                portal_id=portal.id,
                resolved_corporate_website="https://example.test",
                resolved_careers_landing_url="https://example.test/careers",
                source_jobs_search_url=portal.jobs_search_url,
                portal_scope="Global",
                ats_family="fixture",
                ats_confidence="Verified",
                portal_resolution_status="VERIFIED_WAVE_TEST",
                portal_verification_url=portal.jobs_search_url,
                portal_verified_date=date(2026, 8, 30),
                resolution_parent_override="",
                resolution_wave="TEST",
                source_record_count=1,
                import_batch_id=batch.id,
            )
        )
        return portal.id, cluster.corporate_cluster_id


def _job(
    *,
    source: str = "fixture",
    source_job_id: str = "job-1",
    apply_url: str = "https://jobs.example.test/openings/job-1/apply",
    description: str = "Work in incident response.",
    location: str = "Milan, Italy",
    city: str = "Milan",
) -> RawJob:
    return RawJob(
        source=source,
        source_job_id=source_job_id,
        source_url=apply_url.removesuffix("/apply"),
        apply_url=apply_url,
        title="Junior Security Analyst",
        company="Example Ltd",
        location=location,
        country="IT",
        city=city,
        description=description,
        employment_type="FullTime",
        workplace_type="hybrid",
        ats_job_id="ATS-1" if source == "fixture" else None,
        requisition_id="SEC-1",
        raw_payload={"id": source_job_id, "description": description},
    )


def _scan_summary(
    engine: Engine,
    *,
    portal_id: int,
    jobs: tuple[RawJob, ...],
    portal_status: str = "SUCCESS",
    complete_snapshot: bool = True,
) -> ScanSummary:
    now = datetime.now(UTC)
    with Session(engine) as session, session.begin():
        run = ScanRun(
            source="test",
            status="COMPLETED" if portal_status == "SUCCESS" else "COMPLETED_WITH_ERRORS",
            started_at=now,
            finished_at=now,
            portal_count=1,
            success_count=int(portal_status == "SUCCESS"),
            failure_count=int(portal_status != "SUCCESS"),
            jobs_discovered=len(jobs),
            pipeline_status="NOT_PROCESSED",
        )
        session.add(run)
        session.flush()
        portal = session.get(Portal, portal_id)
        assert portal is not None
        target = PortalTarget(
            portal_id=portal.id,
            jobs_search_url=portal.jobs_search_url,
            normalized_jobs_url=portal.normalized_jobs_url,
            host=portal.host,
            ats_families=("fixture",),
            ats_confidences=("Verified",),
        )
        result = PortalScanResult(
            target=target,
            adapter="fixture",
            status=portal_status,
            started_at=now,
            finished_at=now,
            jobs=jobs,
            fetch_attempts=(),
            retry_count=0,
            final_http_status=(200 if portal_status == "SUCCESS" else 500),
            response_sha256=None,
            cache_hit=False,
            complete_snapshot=complete_snapshot,
            error_type=(None if portal_status == "SUCCESS" else "FixtureError"),
            error_message=(None if portal_status == "SUCCESS" else "failed"),
        )
        return ScanSummary(
            scan_run_id=run.id,
            status=run.status,
            portal_count=1,
            success_count=run.success_count,
            failure_count=run.failure_count,
            request_count=0,
            retry_count=0,
            jobs_discovered=len(jobs),
            portal_results=(result,),
        )


def test_processing_persists_provenance_and_target_job(sqlite_engine: Engine) -> None:
    portal_id, cluster_id = _seed_registry(sqlite_engine)
    scan = _scan_summary(sqlite_engine, portal_id=portal_id, jobs=(_job(),))
    summary = process_scan_results(sqlite_engine, scan)

    assert summary.observations == 1
    assert summary.included == 1
    assert summary.new_canonical_jobs == 1
    assert summary.unresolved_cluster_jobs == 0

    with Session(sqlite_engine) as session:
        source = session.scalar(select(SourceJob))
        canonical = session.scalar(select(CanonicalJob))
        observation = session.scalar(select(JobObservation))
        run = session.get(ScanRun, scan.scan_run_id)
        assert source is not None and source.is_active
        assert canonical is not None and canonical.active
        assert canonical.corporate_cluster_id == cluster_id
        assert canonical.filter_status == "INCLUDE"
        assert canonical.seniority == "junior"
        assert canonical.cyber_category == "general_security"
        assert canonical.country == "Italy"
        assert source.canonical_job_id == canonical.canonical_job_id
        assert observation is not None and observation.payload_changed
        assert observation.raw_payload_json is not None
        assert run is not None and run.pipeline_status == "COMPLETED"
        config_snapshot = json.loads(run.config_snapshot_json or "{}")
        assert set(config_snapshot["filter"]) == {"cyber", "seniority", "geography"}


def test_reclassification_uses_stored_jobs_without_losing_source_adapter(
    sqlite_engine: Engine,
) -> None:
    portal_id, _ = _seed_registry(sqlite_engine)
    initial = _scan_summary(sqlite_engine, portal_id=portal_id, jobs=(_job(),))
    process_scan_results(sqlite_engine, initial)

    with Session(sqlite_engine) as session, session.begin():
        source = session.scalar(select(SourceJob))
        assert source is not None
        source.raw_title = "Writer, Threat Intelligence & Communications"
        source.raw_description = "Write CTI reports."

    summary = reclassify_current_jobs(sqlite_engine)

    assert summary.observations == 1
    assert summary.excluded == 1
    assert summary.closed_canonical_jobs == 1
    with Session(sqlite_engine) as session:
        source = session.scalar(select(SourceJob))
        canonical = session.scalar(select(CanonicalJob))
        run = session.get(ScanRun, summary.scan_run_id)
        assert source is not None and source.adapter == "fixture"
        assert source.canonical_job_id is None
        assert source.is_active
        assert canonical is not None and not canonical.active
        assert run is not None and run.source == "taxonomy_reclassification"
        assert run.request_count == 0


def test_cross_source_observations_share_one_canonical_job(sqlite_engine: Engine) -> None:
    portal_id, _ = _seed_registry(sqlite_engine)
    shared_apply = "https://jobs.example.test/openings/job-1/apply"
    scan = _scan_summary(
        sqlite_engine,
        portal_id=portal_id,
        jobs=(
            _job(apply_url=shared_apply),
            _job(source="linkedin", source_job_id="li-1", apply_url=shared_apply),
        ),
    )
    summary = process_scan_results(sqlite_engine, scan)

    assert summary.new_canonical_jobs == 1
    assert summary.duplicate_observations == 1
    with Session(sqlite_engine) as session:
        assert session.scalar(select(func.count()).select_from(CanonicalJob)) == 1
        assert session.scalar(select(func.count()).select_from(SourceJob)) == 2
        assert session.scalar(select(func.count()).select_from(JobObservation)) == 2


def test_lifecycle_requires_repeated_successful_absence_and_reopens(
    sqlite_engine: Engine,
) -> None:
    portal_id, _ = _seed_registry(sqlite_engine)
    initial = _scan_summary(sqlite_engine, portal_id=portal_id, jobs=(_job(),))
    process_scan_results(sqlite_engine, initial)

    failed = _scan_summary(
        sqlite_engine, portal_id=portal_id, jobs=(), portal_status="FAILED"
    )
    process_scan_results(sqlite_engine, failed)
    with Session(sqlite_engine) as session:
        assert session.scalar(select(SourceJob.is_active)) is True
        assert session.scalar(select(SourceJob.missing_successful_scans)) == 0

    for expected_missing in (0, 1):
        empty = _scan_summary(sqlite_engine, portal_id=portal_id, jobs=())
        summary = process_scan_results(sqlite_engine, empty)
        assert summary.empty_portal_anomalies == 1
        with Session(sqlite_engine) as session:
            assert session.scalar(select(SourceJob.is_active)) is True
            assert session.scalar(select(SourceJob.missing_successful_scans)) == expected_missing

    closing = _scan_summary(sqlite_engine, portal_id=portal_id, jobs=())
    closing_summary = process_scan_results(sqlite_engine, closing)
    assert closing_summary.closed_source_jobs == 1
    assert closing_summary.closed_canonical_jobs == 1
    with Session(sqlite_engine) as session:
        assert session.scalar(select(SourceJob.is_active)) is False
        assert session.scalar(select(CanonicalJob.active)) is False

    reopening = _scan_summary(sqlite_engine, portal_id=portal_id, jobs=(_job(),))
    process_scan_results(sqlite_engine, reopening)
    with Session(sqlite_engine) as session:
        assert session.scalar(select(SourceJob.is_active)) is True
        assert session.scalar(select(SourceJob.missing_successful_scans)) == 0
        assert session.scalar(select(CanonicalJob.active)) is True
        assert session.scalar(select(CanonicalJob.closed_at)) is None


def test_processing_same_scan_twice_is_rejected(sqlite_engine: Engine) -> None:
    portal_id, _ = _seed_registry(sqlite_engine)
    scan = _scan_summary(sqlite_engine, portal_id=portal_id, jobs=(_job(),))
    process_scan_results(sqlite_engine, scan)
    try:
        process_scan_results(sqlite_engine, scan)
    except ValueError as exc:
        assert "already been processed" in str(exc)
    else:
        raise AssertionError("Expected idempotency guard")


def test_incomplete_html_snapshots_never_advance_closure(sqlite_engine: Engine) -> None:
    portal_id, _ = _seed_registry(sqlite_engine)
    initial = _scan_summary(sqlite_engine, portal_id=portal_id, jobs=(_job(),))
    process_scan_results(sqlite_engine, initial)

    for _ in range(3):
        partial = _scan_summary(
            sqlite_engine,
            portal_id=portal_id,
            jobs=(),
            complete_snapshot=False,
        )
        process_scan_results(sqlite_engine, partial)

    with Session(sqlite_engine) as session:
        assert session.scalar(select(SourceJob.is_active)) is True
        assert session.scalar(select(SourceJob.missing_successful_scans)) == 0
        assert session.scalar(select(CanonicalJob.active)) is True


def test_v2_discovery_preserves_same_source_id_city_variants(sqlite_engine: Engine) -> None:
    portal_id, _ = _seed_registry(sqlite_engine)
    scan = _scan_summary(
        sqlite_engine,
        portal_id=portal_id,
        jobs=(
            _job(
                source_job_id="shared-123",
                apply_url="https://jobs.example.test/openings/shared-123-milan",
                location="Milan, Italy",
                city="Milan",
            ),
            _job(
                source_job_id="shared-123",
                apply_url="https://jobs.example.test/openings/shared-123-rome",
                location="Rome, Italy",
                city="Rome",
            ),
        ),
    )

    summary = persist_scan_discoveries(sqlite_engine, scan)

    assert summary.observations == 2
    assert summary.new_source_jobs == 2
    assert summary.source_id_collisions_preserved == 1
    with Session(sqlite_engine) as session:
        rows = session.scalars(select(SourceJob).order_by(SourceJob.id)).all()
        assert len(rows) == 2
        assert {row.raw_location for row in rows} == {"Milan, Italy", "Rome, Italy"}
        assert {row.native_source_job_id for row in rows} == {"shared-123"}
        assert len({row.source_job_id for row in rows}) == 2
        assert all(row.ai_status == "PENDING_AI" for row in rows)
        assert all(row.canonical_job_id is None for row in rows)


def test_v2_discovery_does_not_requeue_unchanged_analyzed_job(sqlite_engine: Engine) -> None:
    portal_id, _ = _seed_registry(sqlite_engine)
    first = _scan_summary(sqlite_engine, portal_id=portal_id, jobs=(_job(),))
    persist_scan_discoveries(sqlite_engine, first)
    with Session(sqlite_engine) as session, session.begin():
        source = session.scalar(select(SourceJob))
        assert source is not None
        source.ai_status = "CYBER"

    second = _scan_summary(sqlite_engine, portal_id=portal_id, jobs=(_job(),))
    summary = persist_scan_discoveries(sqlite_engine, second)
    assert summary.unchanged_source_jobs == 1
    with Session(sqlite_engine) as session:
        source = session.scalar(select(SourceJob))
        assert source is not None
        assert source.ai_status == "CYBER"
