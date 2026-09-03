from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from research_agent.db.backup import (
    apply_backup_retention,
    backup_sqlite_database,
    plan_backup_retention,
)
from research_agent.db.migrations import create_schema
from research_agent.db.session import create_db_engine
from research_agent.pipeline.gates import ScanGatePolicy, assess_scan_gate
from research_agent.pipeline.scanner import PortalScanResult, ScanSummary
from research_agent.sources.base import PortalTarget, RawJob


def test_sqlite_backup_is_integrity_checked_and_readable(
    sqlite_engine: Engine, tmp_path: Path
) -> None:
    create_schema(sqlite_engine)
    destination = tmp_path / "backup.db"

    result = backup_sqlite_database(sqlite_engine, destination=destination)

    assert result.path == destination
    assert result.size_bytes > 0
    assert len(result.sha256) == 64
    assert result.integrity_check == "ok"
    backup_engine = create_db_engine(f"sqlite:///{destination}")
    assert "scan_runs" in inspect(backup_engine).get_table_names()


def test_backup_retention_is_dry_run_and_keeps_newest(tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    backups = [backup_dir / f"research_agent_0{index}.db" for index in range(5)]
    for index, path in enumerate(backups):
        path.write_bytes(bytes([index + 1]) * (index + 1))
        path.touch()
    orphan = backup_dir / "old.db.partial-wal"
    orphan.write_bytes(b"orphan")

    plan = plan_backup_retention(backup_dir, keep_last=2)

    assert len(plan.retained) == 2
    assert len(plan.deletable) == 3
    assert orphan.resolve() in plan.orphan_sidecars
    assert all(path.exists() for path in backups)

    result = apply_backup_retention(plan)

    assert len(result.deleted) == 4
    assert all(path.exists() for path in plan.retained)
    assert all(not path.exists() for path in plan.deletable)
    assert not orphan.exists()


def test_scan_gate_blocks_failure_429_and_empty_complete_snapshot() -> None:
    now = datetime.now(UTC)
    target = PortalTarget(
        portal_id=1,
        jobs_search_url="https://jobs.example.test",
        normalized_jobs_url="https://jobs.example.test",
        host="jobs.example.test",
        ats_families=("fixture",),
        ats_confidences=("Verified",),
    )
    empty = PortalScanResult(
        target=target,
        adapter="fixture",
        status="SUCCESS",
        started_at=now,
        finished_at=now,
        jobs=(),
        fetch_attempts=(),
        retry_count=0,
        final_http_status=200,
        response_sha256="a" * 64,
        cache_hit=False,
        complete_snapshot=True,
    )
    failed = PortalScanResult(
        target=target,
        adapter="fixture",
        status="FAILED",
        started_at=now,
        finished_at=now,
        jobs=(),
        fetch_attempts=(),
        retry_count=1,
        final_http_status=429,
        response_sha256=None,
        cache_hit=False,
        complete_snapshot=False,
    )
    scan = ScanSummary(
        scan_run_id=1,
        status="COMPLETED_WITH_ERRORS",
        portal_count=2,
        success_count=1,
        failure_count=1,
        request_count=2,
        retry_count=1,
        jobs_discovered=0,
        portal_results=(empty, failed),
    )

    result = assess_scan_gate(scan, ScanGatePolicy())

    assert result.passed is False
    assert result.failure_rate == 0.5
    assert result.retry_rate == 0.5
    assert result.unexpected_empty_complete == 1
    assert len(result.reasons) == 3


def test_scan_gate_accepts_healthy_nonempty_cohort() -> None:
    now = datetime.now(UTC)
    target = PortalTarget(
        portal_id=1,
        jobs_search_url="https://jobs.example.test",
        normalized_jobs_url="https://jobs.example.test",
        host="jobs.example.test",
        ats_families=("fixture",),
        ats_confidences=("Verified",),
    )
    result = PortalScanResult(
        target=target,
        adapter="fixture",
        status="SUCCESS",
        started_at=now,
        finished_at=now,
        jobs=(
            RawJob(
                source="fixture",
                source_job_id="1",
                source_url="https://jobs.example.test/1",
                apply_url="https://jobs.example.test/1",
                title="Junior Security Analyst",
            ),
        ),
        fetch_attempts=(),
        retry_count=0,
        final_http_status=200,
        response_sha256="a" * 64,
        cache_hit=False,
        complete_snapshot=True,
    )
    scan = ScanSummary(
        scan_run_id=1,
        status="COMPLETED",
        portal_count=1,
        success_count=1,
        failure_count=0,
        request_count=1,
        retry_count=0,
        jobs_discovered=1,
        portal_results=(result,),
    )

    assert assess_scan_gate(scan, ScanGatePolicy()).passed is True


def test_scan_gate_accepts_source_confirmed_empty_snapshot() -> None:
    now = datetime.now(UTC)
    target = PortalTarget(
        portal_id=1,
        jobs_search_url="https://jobs.example.test",
        normalized_jobs_url="https://jobs.example.test",
        host="jobs.example.test",
        ats_families=("fixture",),
        ats_confidences=("Verified",),
    )
    empty = PortalScanResult(
        target=target,
        adapter="fixture",
        status="SUCCESS",
        started_at=now,
        finished_at=now,
        jobs=(),
        fetch_attempts=(),
        retry_count=0,
        final_http_status=200,
        response_sha256="a" * 64,
        cache_hit=False,
        complete_snapshot=True,
        warnings=("upstream reports zero active jobs",),
    )
    scan = ScanSummary(
        scan_run_id=1,
        status="COMPLETED",
        portal_count=1,
        success_count=1,
        failure_count=0,
        request_count=1,
        retry_count=0,
        jobs_discovered=0,
        portal_results=(empty,),
    )

    gate = assess_scan_gate(scan, ScanGatePolicy())
    assert gate.passed is True
    assert gate.unexpected_empty_complete == 0
