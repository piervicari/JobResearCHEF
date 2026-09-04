import csv
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_agent.company.importer import MASTER_HEADERS, import_master, read_master
from research_agent.company.registry_changes import (
    CHANGE_HEADERS,
    RegistryChangeError,
    apply_registry_changes,
    export_synchronized_master,
)
from research_agent.db.migrations import create_schema
from research_agent.db.models import (
    ClusterPortalMapping,
    CompanyRecord,
    CorporateCluster,
    ImportBatch,
    Portal,
    RegistryChangeAudit,
)
from research_agent.pipeline.scanner import load_portal_targets


def _master_row(record_id: str, cluster_id: str, *, resolved: bool) -> dict[str, str]:
    row = {header: "" for header in MASTER_HEADERS}
    row.update(
        {
            "Record ID": record_id,
            "Employer": f"Employer {record_id}",
            "Canonical Employer": f"Employer {record_id}",
            "Corporate Cluster ID": cluster_id,
            "Entity Class": "Company",
            "Career Scan Eligible": "Yes",
            "Sector": "Technology",
            "Discovery Geography": "Italy",
            "Org Type": "Company",
            "Career Scan Status": "READY" if resolved else "NOT_STARTED",
            "Discovery Source": "fixture",
            "Source URL": "https://source.example.test",
            "Freeze Version": "v1",
            "Freeze Status": "FROZEN_WITH_KNOWN_RESIDUALS",
            "Portal Resolution Status": "NOT_STARTED",
        }
    )
    if resolved:
        row.update(
            {
                "Resolved Corporate Website": "https://one.example.test",
                "Resolved Careers Landing URL": "https://one.example.test/careers",
                "Resolved Jobs Search URL": "https://old.example.test/jobs",
                "Portal Scope": "Global",
                "ATS Family": "Fixture ATS",
                "ATS Confidence": "Verified",
                "Portal Resolution Status": "VERIFIED",
                "Portal Verification URL": "https://one.example.test/careers",
                "Portal Verified Date": "2026-08-31",
                "Resolution Wave": "W1",
            }
        )
    return row


def _write_csv(path: Path, headers: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def _change(
    action: str,
    cluster_id: str,
    *,
    old_url: str = "",
    new_host: str = "",
) -> dict[str, str]:
    row = {header: "" for header in CHANGE_HEADERS}
    row.update(
        {
            "Action": action,
            "Corporate Cluster ID": cluster_id,
            "Old Jobs Search URL": old_url,
            "Portal Verification URL": "https://evidence.example.test/careers",
            "Portal Verified Date": "2026-08-31",
            "Reason": f"fixture {action.casefold()}",
        }
    )
    if action in {"ADD", "UPDATE"}:
        row.update(
            {
                "Resolved Corporate Website": f"https://{new_host}",
                "Resolved Careers Landing URL": f"https://{new_host}/careers",
                "Resolved Jobs Search URL": f"https://{new_host}/jobs",
                "Portal Scope": "Global",
                "ATS Family": "Fixture ATS 2",
                "ATS Confidence": "Verified",
                "Portal Resolution Status": "VERIFIED",
                "Resolution Wave": "W6",
            }
        )
    return row


def _seed_master(engine: Engine, tmp_path: Path) -> Path:
    path = tmp_path / "master.csv"
    _write_csv(
        path,
        MASTER_HEADERS,
        [
            _master_row("R1", "CG-1", resolved=True),
            _master_row("R2", "CG-2", resolved=False),
        ],
    )
    import_master(engine, path, source_version="fixture-v1")
    return path


def test_registry_changes_update_add_export_and_remain_idempotent(
    sqlite_engine: Engine, tmp_path: Path
) -> None:
    _seed_master(sqlite_engine, tmp_path)
    changes = tmp_path / "changes.csv"
    _write_csv(
        changes,
        CHANGE_HEADERS,
        [
            _change(
                "UPDATE",
                "CG-1",
                old_url="https://old.example.test/jobs",
                new_host="new.example.test",
            ),
            _change("ADD", "CG-2", new_host="two.example.test"),
        ],
    )

    first = apply_registry_changes(sqlite_engine, changes, source_version="fixture-w6")
    second = apply_registry_changes(sqlite_engine, changes, source_version="fixture-w6")

    assert first.already_applied is False
    assert first.action_counts == {"UPDATE": 1, "ADD": 1}
    assert first.before_metrics.resolved_clusters == 1
    assert first.after_metrics.resolved_clusters == 2
    assert first.after_metrics.unique_resolved_jobs_urls == 2
    assert second.already_applied is True
    assert second.import_batch_id == first.import_batch_id

    with Session(sqlite_engine) as session:
        assert session.scalar(select(func.count()).select_from(RegistryChangeAudit)) == 2
        old_portal = session.scalar(
            select(Portal).where(Portal.host == "old.example.test")
        )
        assert old_portal is not None
        assert old_portal.active_in_registry is False
        assert session.scalar(
            select(func.count())
            .select_from(Portal)
            .where(Portal.active_in_registry.is_(True))
        ) == 2

    output = export_synchronized_master(sqlite_engine, tmp_path / "synchronized.csv")
    rows = read_master(output)
    by_cluster = {row["Corporate Cluster ID"]: row for row in rows}
    assert by_cluster["CG-1"]["Resolved Jobs Search URL"] == "https://new.example.test/jobs"
    assert by_cluster["CG-2"]["Resolution Wave"] == "W6"


def test_registry_retire_preserves_old_portal_and_clears_current_resolution(
    sqlite_engine: Engine, tmp_path: Path
) -> None:
    _seed_master(sqlite_engine, tmp_path)
    changes = tmp_path / "retire.csv"
    _write_csv(
        changes,
        CHANGE_HEADERS,
        [
            _change(
                "RETIRE",
                "CG-1",
                old_url="https://old.example.test/jobs",
            )
        ],
    )

    result = apply_registry_changes(sqlite_engine, changes, source_version="fixture-retire")

    assert result.after_metrics.resolved_clusters == 0
    assert result.after_metrics.unique_resolved_jobs_urls == 0
    with Session(sqlite_engine) as session:
        assert session.scalar(select(func.count()).select_from(Portal)) == 1
        assert session.scalar(select(func.count()).select_from(ClusterPortalMapping)) == 0
        record = session.scalar(
            select(CompanyRecord).where(CompanyRecord.corporate_cluster_id == "CG-1")
        )
        assert record is not None
        assert record.resolution_wave == ""
        assert record.resolved_jobs_search_url == ""


def test_registry_change_old_url_mismatch_rolls_back_batch(
    sqlite_engine: Engine, tmp_path: Path
) -> None:
    _seed_master(sqlite_engine, tmp_path)
    changes = tmp_path / "invalid.csv"
    _write_csv(
        changes,
        CHANGE_HEADERS,
        [
            _change(
                "UPDATE",
                "CG-1",
                old_url="https://wrong.example.test/jobs",
                new_host="new.example.test",
            )
        ],
    )

    with pytest.raises(RegistryChangeError, match="old URL mismatch"):
        apply_registry_changes(sqlite_engine, changes, source_version="fixture-invalid")

    with Session(sqlite_engine) as session:
        assert session.scalar(select(func.count()).select_from(ImportBatch)) == 1
        mapping = session.scalar(select(ClusterPortalMapping))
        assert mapping is not None
        assert mapping.source_jobs_search_url == "https://old.example.test/jobs"


def test_registry_suspend_and_resume_preserve_resolution(
    sqlite_engine: Engine, tmp_path: Path
) -> None:
    _seed_master(sqlite_engine, tmp_path)
    suspend = tmp_path / "suspend.csv"
    suspend_row = _change(
        "SUSPEND",
        "CG-1",
        old_url="https://old.example.test/jobs",
    )
    suspend_row["Reason"] = "robots denied during bounded canary"
    _write_csv(suspend, CHANGE_HEADERS, [suspend_row])

    apply_registry_changes(sqlite_engine, suspend, source_version="fixture-suspend")

    assert load_portal_targets(sqlite_engine) == []
    with Session(sqlite_engine) as session:
        portal = session.scalar(select(Portal))
        assert portal is not None
        assert portal.active_in_registry is True
        assert portal.scan_enabled is False
        assert portal.access_state == "ROBOTS_DENIED"
        assert session.scalar(select(func.count()).select_from(ClusterPortalMapping)) == 1

    resume = tmp_path / "resume.csv"
    resume_row = _change(
        "RESUME",
        "CG-1",
        old_url="https://old.example.test/jobs",
    )
    resume_row["Reason"] = "new public contract reviewed"
    _write_csv(resume, CHANGE_HEADERS, [resume_row])
    apply_registry_changes(sqlite_engine, resume, source_version="fixture-resume")

    assert len(load_portal_targets(sqlite_engine)) == 1


def test_load_portal_targets_include_disabled_explicit_only(
    sqlite_engine: Engine, tmp_path: Path
) -> None:
    """include_disabled is allowed only with an explicit portal_ids set; the DB
    is never mutated, and the next normal load_portal_targets call still hides
    the disabled portal."""
    create_schema(sqlite_engine)

    # 1) Seed one CorporateCluster + one Portal directly so we don't depend on
    #    the master-import / registry-changes flow (this test is about the
    #    loader behaviour, not the upstream sync).
    with Session(sqlite_engine) as session, session.begin():
        batch = ImportBatch(
            source_kind="test",
            source_filename="loader-fixture.csv",
            source_path="loader-fixture.csv",
            source_sha256="a" * 64,
            source_version="loader-fixture-v1",
            status="COMPLETE",
        )
        session.add(batch)
        session.flush()
        session.add(
            CorporateCluster(
                corporate_cluster_id="CG-LOAD-1",
                representative_canonical_employer="Fixture Inc.",
                canonical_employers_json="[\"Fixture Inc.\"]",
                parent_groups_json="[]",
                entity_classes_json="[]",
                eligibility_values_json="[]",
                sectors_json="[]",
                discovery_geographies_json="[]",
                org_types_json="[]",
                record_count=1,
                has_primary_scan_eligibility=True,
                import_batch_id=batch.id,
            )
        )
        portal = Portal(
            normalized_jobs_url="https://disabled.example.test/jobs",
            jobs_search_url="https://disabled.example.test/jobs",
            scheme="https",
            host="disabled.example.test",
            ats_families_json="[\"Fixture ATS 2\"]",
            ats_confidences_json="[\"Verified\"]",
            metadata_conflict=False,
            cluster_count=1,
            active_in_registry=True,
            health_state="HEALTHY",
            consecutive_failures=0,
            scan_enabled=True,
            import_batch_id=batch.id,
        )
        session.add(portal)
        session.flush()
        session.add(
            ClusterPortalMapping(
                corporate_cluster_id="CG-LOAD-1",
                portal_id=portal.id,
                resolved_corporate_website="https://disabled.example.test",
                resolved_careers_landing_url="https://disabled.example.test/careers",
                source_jobs_search_url="https://disabled.example.test/jobs",
                portal_scope="Global",
                ats_family="Fixture ATS 2",
                ats_confidence="Verified",
                portal_resolution_status="VERIFIED",
                portal_verification_url="https://evidence.example.test/careers",
                portal_verified_date=date(2026, 8, 31),
                resolution_wave="W1",
                source_record_count=1,
                import_batch_id=batch.id,
            )
        )
        disabled_id = portal.id

    # 2) Flip scan_enabled to False directly to simulate a "READY_TO_PROBE"
    #    portal that the sync has not yet promoted. (We use SQL instead of
    #    apply_registry_changes to keep this test laser-focused on the loader.)
    with Session(sqlite_engine) as session, session.begin():
        session.execute(
            Portal.__table__.update().where(Portal.id == disabled_id).values(scan_enabled=False)
        )

    # 3) Normal loader hides the disabled portal.
    assert load_portal_targets(sqlite_engine) == []

    # 4) include_disabled without portal_ids is rejected.
    with pytest.raises(ValueError, match="include_disabled requires an explicit portal_ids set"):
        load_portal_targets(sqlite_engine, include_disabled=True)

    # 5) include_disabled with explicit portal_ids returns the disabled
    #    portal without mutating the database.
    with_disabled = load_portal_targets(
        sqlite_engine, portal_ids={disabled_id}, include_disabled=True
    )
    assert len(with_disabled) == 1
    assert with_disabled[0].portal_id == disabled_id

    with Session(sqlite_engine) as session:
        still_disabled = session.scalar(select(Portal).where(Portal.id == disabled_id))
        assert still_disabled.scan_enabled is False  # DB unchanged
        # mapping is still there
        assert session.scalar(
            select(func.count()).select_from(ClusterPortalMapping)
            .where(ClusterPortalMapping.portal_id == disabled_id)
        ) == 1
