from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_agent.db.migrations import create_schema
from research_agent.db.models import (
    CanonicalJob,
    CorporateCluster,
    ImportBatch,
    Portal,
    SourceJob,
)
from research_agent.sources.linkedin.importer import (
    LinkedInImportError,
    ingest_linkedin_csv,
    read_linkedin_csv,
)

HEADER = (
    "linkedin_job_id,title,company,location,country,description,posted_at,source_url,"
    "apply_url,employment_type,workplace_type,requisition_id\n"
)


def _seed_company(engine: Engine) -> None:
    create_schema(engine)
    with Session(engine) as session, session.begin():
        batch = ImportBatch(
            source_kind="authoritative_company_master",
            source_filename="fixture.csv",
            source_path="fixture.csv",
            source_sha256="b" * 64,
            source_version="test",
            status="COMPLETED",
            finished_at=datetime(2026, 8, 30, tzinfo=UTC),
        )
        session.add(batch)
        session.flush()
        session.add(
            CorporateCluster(
                corporate_cluster_id="CG-LINKEDIN",
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
        )


def _write_csv(path: Path) -> None:
    path.write_text(
        HEADER
        + "123,Junior Cybersecurity Analyst,Example Ltd,Milano,IT,Incident response "
        "internship,2026-08-20T10:00:00Z,https://www.linkedin.com/jobs/view/123,"
        "https://example.test/jobs/123,Internship,hybrid,SEC-123\n",
        encoding="utf-8",
    )


def test_manual_linkedin_import_uses_pipeline_without_adding_portal(
    sqlite_engine: Engine, tmp_path: Path
) -> None:
    _seed_company(sqlite_engine)
    csv_path = tmp_path / "linkedin.csv"
    _write_csv(csv_path)

    first = ingest_linkedin_csv(sqlite_engine, csv_path)
    second = ingest_linkedin_csv(sqlite_engine, csv_path)

    assert first.already_imported is False
    assert first.processing is not None
    assert first.processing.included == 1
    assert first.processing.new_canonical_jobs == 1
    assert second.already_imported is True
    with Session(sqlite_engine) as session:
        assert session.scalar(select(func.count()).select_from(Portal)) == 0
        source = session.scalar(select(SourceJob))
        canonical = session.scalar(select(CanonicalJob))
        assert source is not None and source.portal_id is None
        assert source.source == "linkedin_manual"
        assert canonical is not None
        assert canonical.corporate_cluster_id == "CG-LINKEDIN"
        assert canonical.country == "Italy"


def test_linkedin_csv_can_extract_job_id_from_url(tmp_path: Path) -> None:
    path = tmp_path / "linkedin.csv"
    path.write_text(
        HEADER
        + ",Cybersecurity Intern,Example Ltd,Rome,IT,,,"
        "https://www.linkedin.com/jobs/view/987654321,,,,\n",
        encoding="utf-8",
    )
    jobs = read_linkedin_csv(path)
    assert jobs[0].source_job_id == "987654321"


def test_linkedin_csv_schema_is_strict(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("title,company\nRole,Example\n", encoding="utf-8")
    with pytest.raises(LinkedInImportError, match="Expected CSV headers"):
        read_linkedin_csv(path)
