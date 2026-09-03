import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_agent.company.importer import import_master, read_master
from research_agent.company.registry_changes import apply_registry_changes
from research_agent.company.validation import validate_database
from research_agent.config import AcceptanceSettings
from research_agent.db.models import (
    ClusterPortalMapping,
    CompanyRecord,
    CorporateCluster,
    ImportBatch,
    Portal,
)


def test_authoritative_master_import_acceptance(sqlite_engine: Engine, master_path: Path) -> None:
    result = import_master(sqlite_engine, master_path)

    assert result.already_imported is False
    assert result.metrics.master_rows == 12_503
    assert result.metrics.unique_record_ids == 12_503
    assert result.metrics.corporate_clusters == 11_798
    assert result.metrics.resolved_rows == 1_263
    assert result.metrics.resolved_clusters == 575
    assert result.metrics.unique_resolved_jobs_urls == 510
    assert result.metrics.cluster_portal_mappings == 575

    with Session(sqlite_engine) as session:
        assert session.scalar(select(func.sum(ClusterPortalMapping.source_record_count))) == 1_263
        assert (
            session.scalar(
                select(func.count()).select_from(Portal).where(Portal.metadata_conflict.is_(True))
            )
            == 6
        )
        assert (
            session.scalar(
                select(func.count()).select_from(CompanyRecord).where(CompanyRecord.record_id == "")
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(CompanyRecord)
                .where(CompanyRecord.corporate_cluster_id == "")
            )
            == 0
        )


def test_import_is_idempotent(sqlite_engine: Engine, master_path: Path) -> None:
    first = import_master(sqlite_engine, master_path)
    second = import_master(sqlite_engine, master_path)

    assert second.already_imported is True
    assert second.import_batch_id == first.import_batch_id
    assert second.metrics == first.metrics
    with Session(sqlite_engine) as session:
        assert session.scalar(select(func.count()).select_from(ImportBatch)) == 1


def test_cluster_aggregation_preserves_multi_value_provenance(
    sqlite_engine: Engine, master_path: Path
) -> None:
    import_master(sqlite_engine, master_path)
    with Session(sqlite_engine) as session:
        cluster = session.get(CorporateCluster, "CG-FD061ADF6F")
        assert cluster is not None
        canonical_names = json.loads(cluster.canonical_employers_json)
        geographies = json.loads(cluster.discovery_geographies_json)
        assert "Citigroup" in canonical_names
        assert "Citibank Australia" in canonical_names
        assert "Italy" in geographies
        assert "Australia" in geographies
        assert cluster.record_count == 14


def test_validation_gate_passes(sqlite_engine: Engine, master_path: Path) -> None:
    import_master(sqlite_engine, master_path)
    result = validate_database(sqlite_engine, AcceptanceSettings(), master_path)

    assert result.passed is True
    assert all(check.passed for check in result.checks)
    assert result.source_checksum_valid is True
    assert result.portal_metadata_conflicts == 6


def test_validation_uses_immutable_import_snapshot_after_registry_change(
    sqlite_engine: Engine,
    master_path: Path,
    tmp_path: Path,
) -> None:
    import_master(sqlite_engine, master_path)
    change = tmp_path / "retire.csv"
    change.write_text(
        "Action,Corporate Cluster ID,Old Jobs Search URL,Resolved Corporate Website,"
        "Resolved Careers Landing URL,Resolved Jobs Search URL,Portal Scope,ATS Family,"
        "ATS Confidence,Portal Resolution Status,Portal Verification URL,Portal Verified Date,"
        "Resolution Parent Override,Resolution Wave,Reason\n"
        "RETIRE,CG-2E3CAF15E7,https://www.careers.jnj.com/jobs,,,,,,,,"
        "https://www.careers.jnj.com/jobs,2026-08-31,,,Fixture retirement\n",
        encoding="utf-8",
    )
    apply_registry_changes(sqlite_engine, change, source_version="test-retire")

    result = validate_database(sqlite_engine, AcceptanceSettings(), master_path)

    assert result.passed is True
    assert result.database_metrics.unique_resolved_jobs_urls == 510
    assert result.current_database_metrics.unique_resolved_jobs_urls == 509


def test_source_rows_are_complete_and_schema_strict(master_path: Path) -> None:
    rows = read_master(master_path)
    assert len(rows) == 12_503
    assert {row["Freeze Status"] for row in rows} == {"FROZEN_WITH_KNOWN_RESIDUALS"}
    assert sum(row["Career Scan Eligible"] == "Yes" for row in rows) == 12_437
    assert sum(row["Career Scan Eligible"] == "Secondary" for row in rows) == 66
