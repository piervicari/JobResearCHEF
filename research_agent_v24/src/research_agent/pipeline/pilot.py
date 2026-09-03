"""Disposable P0 pilot database helpers.

A pilot DB preserves the company/portal registry but removes historical job/run state so
an end-to-end cohort test measures only discoveries produced by the current pilot.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_agent.db.backup import backup_sqlite_database
from research_agent.db.migrations import create_schema
from research_agent.db.models import (
    CanonicalJob,
    JobAiAnalysis,
    JobObservation,
    Portal,
    PortalScanAttempt,
    ScanRun,
    SourceJob,
)


@dataclass(frozen=True)
class PilotDbSummary:
    path: Path
    integrity_check: str
    source_jobs: int
    canonical_jobs: int
    scan_runs: int


def prepare_pilot_database(
    source_engine: Engine,
    destination: Path,
    *,
    replace: bool = False,
) -> PilotDbSummary:
    """Copy the registry DB and clear all job/run state without external requests."""

    destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if not replace:
            raise FileExistsError(f"pilot DB already exists: {destination}")
        destination.unlink()
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{destination}{suffix}")
            if sidecar.exists():
                sidecar.unlink()

    result = backup_sqlite_database(source_engine, destination=destination)

    from research_agent.db.session import create_db_engine

    pilot_engine = create_db_engine(f"sqlite:///{destination}")
    create_schema(pilot_engine)
    with Session(pilot_engine) as session, session.begin():
        # Child tables first; keeping the registry/import tables makes the DB immediately scannable.
        session.execute(delete(JobAiAnalysis))
        session.execute(delete(JobObservation))
        session.execute(delete(SourceJob))
        session.execute(delete(CanonicalJob))
        session.execute(delete(PortalScanAttempt))
        session.execute(delete(ScanRun))
        session.execute(
            update(Portal).values(
                last_http_status=None,
                last_redirect_target=None,
                last_successful_scan_at=None,
                last_failure_at=None,
                consecutive_failures=0,
                consecutive_empty_scans=0,
                cooldown_until=None,
                last_block_reason=None,
                health_state="UNKNOWN",
            )
        )

    with Session(pilot_engine) as session:
        source_jobs = session.query(SourceJob).count()
        canonical_jobs = session.query(CanonicalJob).count()
        scan_runs = session.query(ScanRun).count()

    return PilotDbSummary(
        path=destination,
        integrity_check=result.integrity_check,
        source_jobs=source_jobs,
        canonical_jobs=canonical_jobs,
        scan_runs=scan_runs,
    )
