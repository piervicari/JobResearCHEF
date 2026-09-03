import json
from datetime import date

from sqlalchemy.orm import Session

from research_agent.company.wave6 import select_wave6_candidates
from research_agent.db.migrations import create_schema
from research_agent.db.models import (
    ClusterPortalMapping,
    CorporateCluster,
    ImportBatch,
    Portal,
)


def test_wave6_selection_is_deterministic_and_excludes_resolved(sqlite_engine) -> None:
    create_schema(sqlite_engine)
    with Session(sqlite_engine) as session, session.begin():
        batch = ImportBatch(
            source_kind="test",
            source_filename="test.csv",
            source_path="test.csv",
            source_sha256="1" * 64,
            source_version="test",
            status="COMPLETED",
        )
        session.add(batch)
        session.flush()
        candidates = [
            _cluster(batch.id, "CG-CYBER", "Acme Cyber Security", "Cybersecurity vendors"),
            _cluster(
                batch.id,
                "CG-LARGE",
                "Large Group",
                "Cross-sector large-cap employer baseline",
            ),
            _cluster(batch.id, "CG-SMALL", "Small Workshop", "Manufacturing"),
        ]
        session.add_all(candidates)
        portal = Portal(
            normalized_jobs_url="https://jobs.example.test/",
            jobs_search_url="https://jobs.example.test/",
            scheme="https",
            host="jobs.example.test",
            ats_families_json='["Test"]',
            ats_confidences_json='["High"]',
            metadata_conflict=False,
            cluster_count=1,
            import_batch_id=batch.id,
        )
        session.add(portal)
        session.flush()
        session.add(
            ClusterPortalMapping(
                corporate_cluster_id="CG-LARGE",
                portal_id=portal.id,
                resolved_corporate_website="https://example.test",
                resolved_careers_landing_url="https://jobs.example.test/",
                source_jobs_search_url="https://jobs.example.test/",
                portal_scope="Test",
                ats_family="Test",
                ats_confidence="High",
                portal_resolution_status="VERIFIED_TEST",
                portal_verification_url="https://jobs.example.test/",
                portal_verified_date=date(2026, 8, 31),
                resolution_parent_override="",
                resolution_wave="TEST",
                source_record_count=1,
                import_batch_id=batch.id,
            )
        )

    first = select_wave6_candidates(sqlite_engine, limit=2)
    second = select_wave6_candidates(sqlite_engine, limit=2)
    assert first == second
    assert [row.corporate_cluster_id for row in first] == ["CG-CYBER", "CG-SMALL"]
    assert first[0].priority_score > first[1].priority_score
    assert all(row.corporate_cluster_id != "CG-LARGE" for row in first)


def _cluster(batch_id: int, cluster_id: str, name: str, sector: str) -> CorporateCluster:
    return CorporateCluster(
        corporate_cluster_id=cluster_id,
        representative_canonical_employer=name,
        canonical_employers_json=json.dumps([name]),
        parent_groups_json="[]",
        entity_classes_json='["Company"]',
        eligibility_values_json='["Yes"]',
        sectors_json=json.dumps([sector]),
        discovery_geographies_json='["Italy"]',
        org_types_json='["Company"]',
        record_count=1,
        has_primary_scan_eligibility=True,
        active_in_master=True,
        import_batch_id=batch_id,
    )
