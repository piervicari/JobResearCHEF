"""Compliant manual LinkedIn job ingestion; no crawling or login automation."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_agent.company.importer import file_sha256
from research_agent.db.migrations import create_schema
from research_agent.db.models import ImportBatch, ScanRun, utc_now
from research_agent.pipeline.lifecycle import ProcessingSummary, process_scan_results
from research_agent.pipeline.scanner import PortalScanResult, ScanSummary
from research_agent.sources.ats.common import parse_datetime
from research_agent.sources.base import PortalTarget, RawJob

LINKEDIN_CSV_HEADERS = (
    "linkedin_job_id",
    "title",
    "company",
    "location",
    "country",
    "description",
    "posted_at",
    "source_url",
    "apply_url",
    "employment_type",
    "workplace_type",
    "requisition_id",
)


class LinkedInImportError(ValueError):
    pass


@dataclass(frozen=True)
class LinkedInImportResult:
    import_batch_id: int
    scan_run_id: int
    rows: int
    already_imported: bool
    processing: ProcessingSummary | None


def read_linkedin_csv(path: Path) -> list[RawJob]:
    with path.expanduser().resolve().open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != LINKEDIN_CSV_HEADERS:
            raise LinkedInImportError(
                f"Expected CSV headers {list(LINKEDIN_CSV_HEADERS)}, "
                f"got {list(reader.fieldnames or ())}"
            )
        rows = list(reader)
    jobs: list[RawJob] = []
    seen_ids: set[str] = set()
    for row_number, row in enumerate(rows, start=2):
        title = row["title"].strip()
        company = row["company"].strip()
        source_url = row["source_url"].strip()
        source_job_id = row["linkedin_job_id"].strip() or _job_id_from_url(source_url)
        if not title or not company or not source_url or not source_job_id:
            raise LinkedInImportError(
                f"Row {row_number} requires title, company, source_url and a resolvable job ID"
            )
        if source_job_id in seen_ids:
            raise LinkedInImportError(f"Duplicate linkedin_job_id {source_job_id!r}")
        seen_ids.add(source_job_id)
        jobs.append(
            RawJob(
                source="linkedin_manual",
                source_job_id=source_job_id,
                source_url=source_url,
                apply_url=row["apply_url"].strip() or source_url,
                title=title,
                company=company,
                location=row["location"].strip(),
                country=row["country"].strip() or None,
                description=row["description"].strip(),
                posted_at=parse_datetime(row["posted_at"]),
                employment_type=row["employment_type"].strip() or None,
                workplace_type=row["workplace_type"].strip() or None,
                requisition_id=row["requisition_id"].strip() or None,
                raw_payload=row,
            )
        )
    return jobs


def ingest_linkedin_csv(
    engine: Engine,
    path: Path,
    *,
    closure_missed_successful_runs: int = 2,
) -> LinkedInImportResult:
    create_schema(engine)
    resolved_path = path.expanduser().resolve()
    source_sha = file_sha256(resolved_path)
    jobs = read_linkedin_csv(resolved_path)
    now = utc_now()

    with Session(engine) as session, session.begin():
        batch = session.scalar(
            select(ImportBatch).where(
                ImportBatch.source_sha256 == source_sha,
                ImportBatch.source_kind == "linkedin_manual_csv",
            )
        )
        if batch is not None:
            run = session.scalar(
                select(ScanRun).where(ScanRun.input_import_batch_id == batch.id)
            )
            if run is None:
                raise LinkedInImportError(f"Import batch {batch.id} has no linked scan run")
            if batch.status == "COMPLETED" and run.pipeline_status == "COMPLETED":
                return LinkedInImportResult(batch.id, run.id, len(jobs), True, None)
            run_id = run.id
            batch_id = batch.id
        else:
            batch = ImportBatch(
                source_kind="linkedin_manual_csv",
                source_filename=resolved_path.name,
                source_path=str(resolved_path),
                source_sha256=source_sha,
                source_version="linkedin-csv-v1",
                status="PARSED",
                row_count=len(jobs),
                started_at=now,
                finished_at=now,
            )
            session.add(batch)
            session.flush()
            run = ScanRun(
                input_import_batch_id=batch.id,
                source="linkedin_manual",
                status="COMPLETED",
                started_at=now,
                finished_at=now,
                portal_count=0,
                success_count=1,
                failure_count=0,
                jobs_discovered=len(jobs),
                pipeline_status="NOT_PROCESSED",
            )
            session.add(run)
            session.flush()
            run_id = run.id
            batch_id = batch.id

    scan = _scan_summary(run_id, jobs, now)
    processing = process_scan_results(
        engine,
        scan,
        closure_missed_successful_runs=closure_missed_successful_runs,
    )
    with Session(engine) as session, session.begin():
        batch = session.get(ImportBatch, batch_id)
        if batch is None:
            raise LinkedInImportError("LinkedIn import batch disappeared")
        batch.status = "COMPLETED"
        batch.validation_json = json.dumps(asdict(processing), sort_keys=True)
    return LinkedInImportResult(batch_id, run_id, len(jobs), False, processing)


def _scan_summary(run_id: int, jobs: list[RawJob], now: datetime) -> ScanSummary:
    target = PortalTarget(
        portal_id=None,
        jobs_search_url="manual://linkedin-csv",
        normalized_jobs_url="manual://linkedin-csv",
        host="local-import",
        ats_families=("LinkedIn manual import",),
        ats_confidences=("User supplied",),
    )
    result = PortalScanResult(
        target=target,
        adapter="linkedin_manual_csv",
        status="SUCCESS",
        started_at=now,
        finished_at=now,
        jobs=tuple(jobs),
        fetch_attempts=(),
        retry_count=0,
        final_http_status=None,
        response_sha256=None,
        cache_hit=False,
        complete_snapshot=False,
    )
    return ScanSummary(
        scan_run_id=run_id,
        status="COMPLETED",
        portal_count=0,
        success_count=1,
        failure_count=0,
        request_count=0,
        retry_count=0,
        jobs_discovered=len(jobs),
        portal_results=(result,),
    )


def _job_id_from_url(value: str) -> str:
    match = re.search(r"/jobs/view/(\d+)", value)
    return match.group(1) if match else ""
