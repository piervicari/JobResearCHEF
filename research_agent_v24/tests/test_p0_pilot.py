from pathlib import Path

from sqlalchemy.orm import Session

from research_agent.db.models import ImportBatch, Portal, SourceJob
from research_agent.db.session import create_db_engine
from research_agent.pipeline.pilot import prepare_pilot_database


def test_prepare_pilot_database_keeps_registry_and_clears_jobs(tmp_path: Path):
    source_path = tmp_path / "source.db"
    source = create_db_engine(f"sqlite:///{source_path}")
    from research_agent.db.migrations import create_schema

    create_schema(source)
    with Session(source) as session, session.begin():
        batch = ImportBatch(
            source_kind="test",
            source_filename="test.csv",
            source_path="test.csv",
            source_sha256="a" * 64,
            source_version="test",
            status="COMPLETE",
        )
        session.add(batch)
        session.flush()
        session.add(
            Portal(
                normalized_jobs_url="https://example.com/jobs",
                jobs_search_url="https://example.com/jobs",
                scheme="https",
                host="example.com",
                ats_families_json="[]",
                ats_confidences_json="[]",
                metadata_conflict=False,
                cluster_count=1,
                active_in_registry=True,
                health_state="HEALTHY",
                consecutive_failures=0,
                import_batch_id=batch.id,
            )
        )
    destination = tmp_path / "pilot.db"
    result = prepare_pilot_database(source, destination, replace=True)
    assert result.integrity_check == "ok"
    pilot = create_db_engine(f"sqlite:///{destination}")
    with Session(pilot) as session:
        assert session.query(Portal).count() == 1
        assert session.query(SourceJob).count() == 0
