from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_agent.company.importer import import_master
from research_agent.dashboard.queries import (
    adapter_coverage_rows,
    classify_portal_issue,
    coverage_summary,
    discovery_coverage_rows,
    high_value_unresolved_rows,
    job_activity_summary,
    job_breakdown_rows,
    job_summary,
    portal_rows,
    review_queue_rows,
    scan_run_rows,
    sector_coverage_rows,
    source_job_rows,
)
from research_agent.db.models import (
    CanonicalJob,
    CorporateCluster,
    Portal,
    PortalScanAttempt,
    ScanRun,
    SourceJob,
    utc_now,
)


def test_dashboard_coverage_and_operational_rows_are_explainable(
    sqlite_engine: Engine,
    master_path: Path,
) -> None:
    import_master(sqlite_engine, master_path)
    coverage = coverage_summary(sqlite_engine)
    portals = portal_rows(sqlite_engine)
    adapters = adapter_coverage_rows(sqlite_engine)
    unresolved = high_value_unresolved_rows(sqlite_engine, limit=10)

    assert coverage.unique_portals == 510
    assert coverage.scanned_portals == 0
    assert coverage.scannable_portals == 510
    assert coverage.stale_portals == 0
    assert len(portals) == 510
    assert {
        "access_state",
        "cooldown_until",
        "latest_warnings",
        "latest_error_type",
        "latest_snapshot_complete",
        "issue_category",
    } <= portals[0].keys()
    assert sum(row["portals"] for row in adapters) == 510
    assert {row["coverage_type"] for row in adapters} == {
        "structured",
        "incomplete fallback",
    }
    assert len(unresolved) == 10
    assert all("priority_score" in row for row in unresolved)
    geography = discovery_coverage_rows(sqlite_engine)
    sectors = sector_coverage_rows(sqlite_engine)
    assert sum(int(row["master_rows"]) for row in geography) == 12_503
    assert sum(int(row["master_rows"]) for row in sectors) == 12_503
    assert all("corporate_clusters" in row for row in (*geography, *sectors))


def test_empty_dashboard_job_queues_are_valid(
    sqlite_engine: Engine,
    master_path: Path,
) -> None:
    import_master(sqlite_engine, master_path)
    assert review_queue_rows(sqlite_engine) == []
    assert source_job_rows(sqlite_engine) == []


def test_dashboard_exposes_required_job_and_run_analytics(
    sqlite_engine: Engine,
    master_path: Path,
) -> None:
    import_master(sqlite_engine, master_path)
    reference = datetime(2026, 9, 1, 12, tzinfo=UTC)

    with Session(sqlite_engine) as session, session.begin():
        cluster = session.scalar(select(CorporateCluster).limit(1))
        portals = session.scalars(select(Portal).order_by(Portal.id).limit(4)).all()
        assert cluster is not None and len(portals) == 4
        cluster_name = cluster.representative_canonical_employer
        run = ScanRun(
            source="official_portals",
            status="COMPLETED_WITH_ERRORS",
            pipeline_status="COMPLETED",
            started_at=reference - timedelta(seconds=12),
            finished_at=reference,
            portal_count=4,
            success_count=2,
            failure_count=2,
            request_count=5,
            retry_count=1,
            http_2xx_count=2,
            http_3xx_count=1,
            http_4xx_count=1,
            http_5xx_count=1,
            http_429_count=0,
            jobs_discovered=3,
            new_jobs=2,
            updated_jobs=1,
            duplicates=1,
            jobs_closed=1,
        )
        session.add(run)
        session.flush()
        attempts = (
            PortalScanAttempt(
                scan_run_id=run.id,
                portal_id=portals[0].id,
                adapter="fixture",
                status="SUCCESS",
                started_at=reference - timedelta(seconds=10),
                finished_at=reference,
                http_status=200,
                jobs_observed=0,
                snapshot_complete=True,
                warnings_json="[]",
            ),
            PortalScanAttempt(
                scan_run_id=run.id,
                portal_id=portals[1].id,
                adapter="fixture",
                status="SUCCESS",
                started_at=reference - timedelta(seconds=10),
                finished_at=reference,
                http_status=200,
                jobs_observed=0,
                snapshot_complete=True,
                warnings_json='["upstream reports zero active jobs"]',
            ),
            PortalScanAttempt(
                scan_run_id=run.id,
                portal_id=portals[2].id,
                adapter="fixture",
                status="FAILED",
                started_at=reference - timedelta(seconds=10),
                finished_at=reference,
                http_status=500,
                error_type="AdapterSchemaError",
                error_message="schema drift",
            ),
            PortalScanAttempt(
                scan_run_id=run.id,
                portal_id=portals[3].id,
                adapter="fixture",
                status="FAILED",
                started_at=reference - timedelta(seconds=10),
                finished_at=reference,
                http_status=404,
                error_type="AdapterHttpError",
                error_message="not found",
            ),
        )
        session.add_all(attempts)

        active = CanonicalJob(
            canonical_job_id="CJ-ACTIVE",
            corporate_cluster_id=cluster.corporate_cluster_id,
            canonical_fingerprint="a" * 64,
            filter_status="INCLUDE",
            primary_apply_url="https://example.test/apply/active",
            title="Cybersecurity Intern",
            normalized_title="cybersecurity intern",
            location="Milan, Italy",
            country="Italy",
            city="Milan",
            workplace_type="hybrid",
            description="Security internship",
            employment_type="Internship",
            seniority="internship",
            cyber_category="security_core",
            first_seen_at=reference - timedelta(hours=1),
            last_seen_at=reference,
            active=True,
            last_seen_successful_run_id=run.id,
        )
        closed = CanonicalJob(
            canonical_job_id="CJ-CLOSED",
            corporate_cluster_id=cluster.corporate_cluster_id,
            canonical_fingerprint="b" * 64,
            filter_status="REVIEW",
            primary_apply_url="https://example.test/apply/closed",
            title="Security Analyst",
            normalized_title="security analyst",
            location="Toronto, Canada",
            country="Canada",
            city="Toronto",
            workplace_type="remote",
            description="Security role",
            employment_type="Full time",
            seniority="junior",
            cyber_category="security_operations",
            first_seen_at=reference - timedelta(days=10),
            last_seen_at=reference - timedelta(days=1),
            active=False,
            closed_at=reference - timedelta(days=1),
            last_seen_successful_run_id=run.id,
        )
        session.add_all((active, closed))
        session.flush()

        def source_job(
            *,
            source_job_id: str,
            source: str,
            canonical_job_id: str,
            portal_id: int | None,
        ) -> SourceJob:
            return SourceJob(
                scan_run_id=run.id,
                portal_id=portal_id,
                canonical_job_id=canonical_job_id,
                source=source,
                source_job_id=source_job_id,
                source_url=f"https://example.test/source/{source_job_id}",
                apply_url=f"https://example.test/apply/{source_job_id}",
                canonical_apply_url=f"https://example.test/apply/{source_job_id}",
                raw_title="Security role",
                raw_company=cluster.representative_canonical_employer,
                raw_location="Italy",
                raw_description="Security",
                fetched_at=reference,
                adapter="fixture",
                parser_version="test",
                payload_sha256=source_job_id.ljust(64, "0"),
                first_seen_at=reference,
                last_seen_at=reference,
                is_active=True,
            )

        session.add_all(
            (
                source_job(
                    source_job_id="official-active",
                    source="official_test",
                    canonical_job_id=active.canonical_job_id,
                    portal_id=portals[0].id,
                ),
                source_job(
                    source_job_id="linkedin-active",
                    source="linkedin_manual",
                    canonical_job_id=active.canonical_job_id,
                    portal_id=None,
                ),
                source_job(
                    source_job_id="official-closed",
                    source="official_test",
                    canonical_job_id=closed.canonical_job_id,
                    portal_id=portals[0].id,
                ),
            )
        )

    summary = job_summary(sqlite_engine)
    assert summary.active_jobs == 1
    assert summary.closed_jobs == 1
    assert summary.found_on_both == 1
    assert summary.official_only == 1

    activity = job_activity_summary(sqlite_engine, period_days=7, now=reference)
    assert activity.latest_run_id == 1
    assert activity.new_jobs_latest_run == 2
    assert activity.new_jobs_today == 1
    assert activity.new_jobs_period == 1

    breakdown = job_breakdown_rows(sqlite_engine)
    active_counts = {
        (str(row["dimension"]), str(row["value"])): int(row["active_jobs"])
        for row in breakdown
    }
    assert active_counts[("Country", "Italy")] == 1
    assert active_counts[("Company", cluster_name)] == 1
    assert active_counts[("Seniority", "internship")] == 1
    assert active_counts[("Workplace", "hybrid")] == 1
    assert active_counts[("Source", "official_test")] == 1
    assert active_counts[("Source", "linkedin_manual")] == 1

    run_row = scan_run_rows(sqlite_engine)[0]
    assert run_row["duration_seconds"] == 12.0
    assert run_row["http_2xx"] == 2
    assert run_row["http_3xx"] == 1
    assert run_row["http_4xx"] == 1
    assert run_row["http_5xx"] == 1
    assert int(run_row["failed_domains"]) >= 1
    assert run_row["parser_failures"] == 1
    assert run_row["unexpected_empty_complete"] == 1

    coverage = coverage_summary(sqlite_engine)
    assert coverage.scanned_portals == 4
    assert coverage.stale_portals == 1


@pytest.mark.parametrize(
    ("error_type", "http_status", "message", "expected"),
    [
        ("RobotsDisallowed", 403, "robots policy", "ROBOTS_DENIAL"),
        ("AccessChallengeError", 403, "challenge", "ACCESS_DENIAL"),
        ("AdapterSchemaError", 200, "missing field", "SCHEMA_DRIFT"),
        ("AdapterHttpError", 404, "not found", "STALE_ROUTE"),
        ("FetchError", None, "timed out", "TRANSIENT_FAILURE"),
    ],
)
def test_portal_issue_categories_are_actionable(
    error_type: str,
    http_status: int | None,
    message: str,
    expected: str,
) -> None:
    portal = Portal(
        id=1,
        normalized_jobs_url="https://jobs.example.test/",
        jobs_search_url="https://jobs.example.test/",
        scheme="https",
        host="jobs.example.test",
        ats_families_json="[]",
        ats_confidences_json="[]",
        metadata_conflict=False,
        cluster_count=1,
        active_in_registry=True,
        health_state="DEGRADED",
        consecutive_failures=1,
        import_batch_id=1,
    )
    attempt = PortalScanAttempt(
        id=1,
        scan_run_id=1,
        portal_id=1,
        adapter="fixture",
        status="FAILED",
        started_at=utc_now(),
        http_status=http_status,
        retries=0,
        jobs_observed=0,
        error_type=error_type,
        error_message=message,
    )
    assert classify_portal_issue(portal, attempt) == expected
