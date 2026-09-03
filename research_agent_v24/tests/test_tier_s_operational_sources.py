"""Tests for the Tier-S Operational Source Control Plane (V25).

Covers the ten scenarios required by the V25 milestone brief.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_agent.company.tier_s_operational_sources import (
    OperationalSourceError,
    REGISTRY_HEADERS,
    SyncReport,
    build_resolution_summary,
    dry_run_sync,
    read_registry,
    reconcile_clusters,
    render_terminal_summary,
    sync_operational_sources,
)
from research_agent.db.models import (
    ClusterPortalMapping,
    ImportBatch,
    JobAiAnalysis,
    Portal,
    SourceJob,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row(
    employer: str,
    cluster_id: str,
    *,
    source_key: str = "main",
    operational: str = "https://boards-api.greenhouse.io/v1/boards/example/jobs?content=true",
    cohort: str = "CORE_200",
    evidence: str = "TECHNICALLY_VERIFIED",
    resolution: str = "READY_TO_PROBE",
    adapter: str = "YES",
    catalog: str = "PARITY_PENDING",
    scan_enabled: str = "N",
) -> dict[str, str]:
    return {
        "employer_name": employer,
        "corporate_cluster_id": cluster_id,
        "priority": "1",
        "cohort": cohort,
        "source_key": source_key,
        "source_scope": "Global",
        "canonical_careers_url": "https://www.example.com/careers/",
        "operational_url": operational,
        "ats_family": "Greenhouse",
        "evidence_state": evidence,
        "resolution_path": resolution,
        "adapter_supported": adapter,
        "catalog_state": catalog,
        "last_verified_at": "2026-09-02",
        "evidence_url": "https://www.example.com/careers/",
        "notes": "fixture",
        "scan_enabled": scan_enabled,
    }


def _write_registry(path: Path, rows: list[dict[str, str]]) -> Path:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REGISTRY_HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow({header: row.get(header, "") for header in REGISTRY_HEADERS})
    return path


def _seed_cluster(engine: Engine, cluster_id: str, representative: str) -> None:
    """Insert a minimal CorporateCluster row directly (no master import)."""

    from research_agent.db.migrations import create_schema
    from research_agent.db.models import CorporateCluster, ImportBatch

    create_schema(engine)
    with Session(engine) as session, session.begin():
        batch = session.scalar(select(ImportBatch))
        if batch is None:
            batch = ImportBatch(
                source_kind="test_fixture",
                source_filename="fixture.csv",
                source_path="/tmp/fixture.csv",
                source_sha256="fixture" + cluster_id,
                source_version="fixture-v1",
                status="COMPLETED",
            )
            session.add(batch)
            session.flush()
        session.add(
            CorporateCluster(
                corporate_cluster_id=cluster_id,
                representative_canonical_employer=representative,
                canonical_employers_json=json.dumps([representative]),
                parent_groups_json=json.dumps([]),
                entity_classes_json=json.dumps(["Company"]),
                eligibility_values_json=json.dumps(["Yes"]),
                sectors_json=json.dumps(["Technology"]),
                discovery_geographies_json=json.dumps(["Global"]),
                org_types_json=json.dumps(["Company"]),
                record_count=1,
                has_primary_scan_eligibility=True,
                active_in_master=True,
                import_batch_id=batch.id,
            )
        )


# ---------------------------------------------------------------------------
# Registry parsing
# ---------------------------------------------------------------------------


def test_registry_rejects_invalid_cohort(tmp_path: Path) -> None:
    bad = tmp_path / "bad.csv"
    _write_registry(bad, [_row("Acme", "CG-1", cohort="NOT_CORE")])
    with pytest.raises(OperationalSourceError, match="invalid cohort"):
        read_registry(bad)


def test_registry_rejects_invalid_resolution_path(tmp_path: Path) -> None:
    bad = tmp_path / "bad.csv"
    _write_registry(bad, [_row("Acme", "CG-1", resolution="FROZEN")])
    with pytest.raises(OperationalSourceError, match="invalid resolution_path"):
        read_registry(bad)


def test_registry_rejects_invalid_operational_url(tmp_path: Path) -> None:
    bad = tmp_path / "bad.csv"
    row = _row("Acme", "CG-1")
    row["operational_url"] = "ftp://nope.example.com/jobs"
    _write_registry(bad, [row])
    with pytest.raises(OperationalSourceError, match="operational_url"):
        read_registry(bad)


# ---------------------------------------------------------------------------
# 1 + 2: one source, two sources for the same cluster
# ---------------------------------------------------------------------------


def test_sync_with_one_source_creates_portal_and_mapping(
    sqlite_engine: Engine, tmp_path: Path
) -> None:
    _seed_cluster(sqlite_engine, "CG-1", "Acme")
    registry = _write_registry(
        tmp_path / "reg.csv",
        [_row("Acme", "CG-1", operational="https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true")],
    )

    rows = read_registry(registry)
    cluster_mapping, unmatched, _ = reconcile_clusters(sqlite_engine, rows)
    assert cluster_mapping == {"Acme": "CG-1"}
    assert unmatched == []

    report = sync_operational_sources(
        sqlite_engine, registry, cluster_mapping=cluster_mapping
    )
    assert isinstance(report, SyncReport)
    assert report.already_applied is False
    assert report.created_portals == 1
    assert report.reused_portals == 0
    assert report.created_mappings == 1
    assert report.updated_mappings == 0
    with Session(sqlite_engine) as session:
        portal = session.scalar(select(Portal))
        assert portal is not None
        assert portal.cluster_count == 1
        assert portal.ats_families_json == json.dumps(["Greenhouse"], separators=(",", ":"))
        mapping = session.scalar(select(ClusterPortalMapping))
        assert mapping is not None
        assert mapping.corporate_cluster_id == "CG-1"
        assert mapping.ats_family == "Greenhouse"


def test_sync_with_two_sources_for_same_cluster_keeps_both(
    sqlite_engine: Engine, tmp_path: Path
) -> None:
    _seed_cluster(sqlite_engine, "CG-2", "Beta")
    registry = _write_registry(
        tmp_path / "reg.csv",
        [
            _row(
                "Beta",
                "CG-2",
                source_key="main",
                operational="https://boards-api.greenhouse.io/v1/boards/beta/jobs?content=true",
            ),
            _row(
                "Beta",
                "CG-2",
                source_key="international",
                operational="https://boards-api.greenhouse.io/v1/boards/betainternational/jobs?content=true",
            ),
        ],
    )

    rows = read_registry(registry)
    cluster_mapping, _, _ = reconcile_clusters(sqlite_engine, rows)
    report = sync_operational_sources(
        sqlite_engine, registry, cluster_mapping=cluster_mapping
    )

    assert report.created_portals == 2
    assert report.created_mappings == 2
    assert "Beta" in report.multi_source_employers
    with Session(sqlite_engine) as session:
        mappings = session.scalars(
            select(ClusterPortalMapping).where(ClusterPortalMapping.corporate_cluster_id == "CG-2")
        ).all()
        urls = sorted(m.source_jobs_search_url for m in mappings)
        assert len(mappings) == 2
        assert any("beta/jobs" in url for url in urls)
        assert any("betainternational/jobs" in url for url in urls)


# ---------------------------------------------------------------------------
# 3: same Portal reused by another cluster where allowed
# ---------------------------------------------------------------------------


def test_same_operational_url_dedupes_as_single_portal(
    sqlite_engine: Engine, tmp_path: Path
) -> None:
    _seed_cluster(sqlite_engine, "CG-3A", "Shared-Cluster-A")
    _seed_cluster(sqlite_engine, "CG-3B", "Shared-Cluster-B")
    registry = _write_registry(
        tmp_path / "reg.csv",
        [
            _row("Shared-Cluster-A", "CG-3A", operational="https://boards-api.greenhouse.io/v1/boards/shared/jobs?content=true"),
            _row("Shared-Cluster-B", "CG-3B", operational="https://boards-api.greenhouse.io/v1/boards/shared/jobs?content=true"),
        ],
    )

    rows = read_registry(registry)
    cluster_mapping, _, _ = reconcile_clusters(sqlite_engine, rows)
    report = sync_operational_sources(
        sqlite_engine, registry, cluster_mapping=cluster_mapping
    )
    assert report.created_portals == 1
    assert report.reused_portals == 1
    assert report.created_mappings == 2
    with Session(sqlite_engine) as session:
        assert session.scalar(select(Portal).where(Portal.host == "boards-api.greenhouse.io")) is not None
        assert (
            session.scalar(
                select(Portal).where(Portal.normalized_jobs_url == "https://boards-api.greenhouse.io/v1/boards/shared/jobs?content=true")
            ).cluster_count
            == 2
        )


# ---------------------------------------------------------------------------
# 4: idempotent repeated sync
# ---------------------------------------------------------------------------


def test_repeated_sync_is_idempotent(
    sqlite_engine: Engine, tmp_path: Path
) -> None:
    _seed_cluster(sqlite_engine, "CG-4", "Gamma")
    registry = _write_registry(
        tmp_path / "reg.csv",
        [_row("Gamma", "CG-4", operational="https://boards-api.greenhouse.io/v1/boards/gamma/jobs?content=true")],
    )

    rows = read_registry(registry)
    cluster_mapping, _, _ = reconcile_clusters(sqlite_engine, rows)
    first = sync_operational_sources(
        sqlite_engine, registry, cluster_mapping=cluster_mapping
    )
    second = sync_operational_sources(
        sqlite_engine, registry, cluster_mapping=cluster_mapping
    )
    third = sync_operational_sources(
        sqlite_engine, registry, cluster_mapping=cluster_mapping
    )
    assert first.already_applied is False
    assert second.already_applied is True
    assert third.already_applied is True
    assert second.import_batch_id == first.import_batch_id == third.import_batch_id
    with Session(sqlite_engine) as session:
        assert session.scalar(select(Portal).where(Portal.host == "boards-api.greenhouse.io")) is not None
        assert (
            session.scalar(
                select(Portal).where(Portal.normalized_jobs_url == "https://boards-api.greenhouse.io/v1/boards/gamma/jobs?content=true")
            ).cluster_count
            == 1
        )
        assert (
            session.scalar(select(ImportBatch).where(ImportBatch.source_kind == "tier_s_operational_sources")) is not None
        )


# ---------------------------------------------------------------------------
# 5: PROBABLE never auto scan-enabled
# ---------------------------------------------------------------------------


def test_probable_does_not_auto_enable_scan(
    sqlite_engine: Engine, tmp_path: Path
) -> None:
    _seed_cluster(sqlite_engine, "CG-5", "Delta")
    registry = _write_registry(
        tmp_path / "reg.csv",
        [
            _row(
                "Delta",
                "CG-5",
                operational="https://boards-api.greenhouse.io/v1/boards/delta/jobs?content=true",
                evidence="PROBABLE",
                resolution="FINGERPRINT_REQUIRED",
                scan_enabled="N",
            )
        ],
    )

    rows = read_registry(registry)
    cluster_mapping, _, _ = reconcile_clusters(sqlite_engine, rows)
    sync_operational_sources(sqlite_engine, registry, cluster_mapping=cluster_mapping)
    with Session(sqlite_engine) as session:
        portal = session.scalar(select(Portal))
        assert portal is not None
        assert portal.scan_enabled is False


# ---------------------------------------------------------------------------
# 6: verified + supported adapter -> READY_TO_PROBE
# ---------------------------------------------------------------------------


def test_verified_with_supported_adapter_lands_in_ready_to_probe(
    sqlite_engine: Engine, tmp_path: Path
) -> None:
    _seed_cluster(sqlite_engine, "CG-6", "Epsilon")
    registry = _write_registry(
        tmp_path / "reg.csv",
        [
            _row(
                "Epsilon",
                "CG-6",
                operational="https://boards-api.greenhouse.io/v1/boards/epsilon/jobs?content=true",
                evidence="TECHNICALLY_VERIFIED",
                resolution="READY_TO_PROBE",
                adapter="YES",
                scan_enabled="N",
            )
        ],
    )

    rows = read_registry(registry)
    cluster_mapping, _, _ = reconcile_clusters(sqlite_engine, rows)
    sync_operational_sources(sqlite_engine, registry, cluster_mapping=cluster_mapping)
    summary = build_resolution_summary(rows, cluster_mapping=cluster_mapping)
    assert summary.ready_to_probe_total == 1
    assert summary.ready_to_probe_by_ats == {"Greenhouse": 1}
    terminal = render_terminal_summary(summary)
    assert "READY_TO_PROBE" in terminal


# ---------------------------------------------------------------------------
# 7: unresolved employer not associated via fuzzy guess
# ---------------------------------------------------------------------------


def test_unresolved_employer_is_not_fuzzy_matched(
    sqlite_engine: Engine, tmp_path: Path
) -> None:
    _seed_cluster(sqlite_engine, "CG-7", "Real Corp")
    registry = _write_registry(
        tmp_path / "reg.csv",
        [
            _row(
                "Not-Really-Related-To-Real-Corp",
                "",
                operational="https://boards-api.greenhouse.io/v1/boards/ghost/jobs?content=true",
            )
        ],
    )

    rows = read_registry(registry)
    cluster_mapping, unmatched, _ = reconcile_clusters(sqlite_engine, rows)
    assert cluster_mapping == {"Not-Really-Related-To-Real-Corp": ""}
    assert len(unmatched) == 1
    assert unmatched[0]["employer"] == "Not-Really-Related-To-Real-Corp"
    assert unmatched[0]["manual_review_required"] == "Y"

    report = sync_operational_sources(
        sqlite_engine, registry, cluster_mapping=cluster_mapping
    )
    assert report.created_portals == 0
    assert report.reused_portals == 0
    assert report.created_mappings == 0
    assert "Not-Really-Related-To-Real-Corp" in report.unmatched_employers
    with Session(sqlite_engine) as session:
        assert session.scalar(select(Portal)) is None
        assert session.scalar(select(ClusterPortalMapping)) is None


# ---------------------------------------------------------------------------
# 8: adding a new source never replaces the previous one
# ---------------------------------------------------------------------------


def test_adding_new_source_keeps_previous_sources_intact(
    sqlite_engine: Engine, tmp_path: Path
) -> None:
    _seed_cluster(sqlite_engine, "CG-8", "Zeta")
    # First sync: single source
    first_registry = _write_registry(
        tmp_path / "first.csv",
        [_row("Zeta", "CG-8", source_key="main", operational="https://boards-api.greenhouse.io/v1/boards/zeta/jobs?content=true")],
    )
    rows1 = read_registry(first_registry)
    cluster_mapping1, _, _ = reconcile_clusters(sqlite_engine, rows1)
    sync_operational_sources(sqlite_engine, first_registry, cluster_mapping=cluster_mapping1)

    # Second sync: add a new international source via a fresh registry file.
    second_registry = _write_registry(
        tmp_path / "second.csv",
        [
            _row("Zeta", "CG-8", source_key="main", operational="https://boards-api.greenhouse.io/v1/boards/zeta/jobs?content=true"),
            _row("Zeta", "CG-8", source_key="international", operational="https://boards-api.greenhouse.io/v1/boards/zetainternational/jobs?content=true"),
        ],
    )
    rows2 = read_registry(second_registry)
    cluster_mapping2, _, _ = reconcile_clusters(sqlite_engine, rows2)
    second = sync_operational_sources(
        sqlite_engine, second_registry, cluster_mapping=cluster_mapping2
    )
    assert second.created_portals == 1
    assert second.reused_portals == 1
    assert second.created_mappings == 1
    assert second.updated_mappings == 1
    with Session(sqlite_engine) as session:
        mappings = session.scalars(
            select(ClusterPortalMapping).where(ClusterPortalMapping.corporate_cluster_id == "CG-8")
        ).all()
        urls = sorted(m.source_jobs_search_url for m in mappings)
        assert len(mappings) == 2
        assert any("zeta/jobs" in url for url in urls)
        assert any("zetainternational/jobs" in url for url in urls)


# ---------------------------------------------------------------------------
# 9: CORE_200 and CORE_EXTENSION remain distinct in the summary
# ---------------------------------------------------------------------------


def test_summary_distinguishes_core_200_and_core_extension(
    sqlite_engine: Engine, tmp_path: Path
) -> None:
    _seed_cluster(sqlite_engine, "CG-9A", "CoreCo")
    _seed_cluster(sqlite_engine, "CG-9B", "ExtensionCo")
    registry = _write_registry(
        tmp_path / "reg.csv",
        [
            _row(
                "CoreCo",
                "CG-9A",
                source_key="main",
                operational="https://boards-api.greenhouse.io/v1/boards/coreco/jobs?content=true",
                cohort="CORE_200",
            ),
            _row(
                "ExtensionCo",
                "CG-9B",
                source_key="main",
                operational="https://boards-api.greenhouse.io/v1/boards/extensionco/jobs?content=true",
                cohort="CORE_EXTENSION",
            ),
        ],
    )
    rows = read_registry(registry)
    cluster_mapping, _, _ = reconcile_clusters(sqlite_engine, rows)
    summary = build_resolution_summary(rows, cluster_mapping=cluster_mapping)
    assert summary.core_200_employers == 1
    assert summary.core_extension_employers == 1


# ---------------------------------------------------------------------------
# 10: legacy VERIFIED (no re-audit) does not auto-FAST_PATH
# ---------------------------------------------------------------------------


def test_legacy_verified_without_audit_v2_evidence_does_not_pass_gating(
    sqlite_engine: Engine, tmp_path: Path
) -> None:
    _seed_cluster(sqlite_engine, "CG-10", "LegacyCo")
    # Old mapping labelled the platform VERIFIED but evidence state is
    # still PROBABLE/UNVERIFIED -> must NOT receive READY_TO_PROBE.
    registry = _write_registry(
        tmp_path / "reg.csv",
        [
            _row(
                "LegacyCo",
                "CG-10",
                operational="https://boards-api.greenhouse.io/v1/boards/legacyco/jobs?content=true",
                evidence="PROBABLE",
                resolution="FINGERPRINT_REQUIRED",
                scan_enabled="N",
            )
        ],
    )
    rows = read_registry(registry)
    cluster_mapping, _, _ = reconcile_clusters(sqlite_engine, rows)
    sync_operational_sources(sqlite_engine, registry, cluster_mapping=cluster_mapping)
    summary = build_resolution_summary(rows, cluster_mapping=cluster_mapping)
    assert summary.ready_to_probe_total == 0
    assert summary.fingerprint_required_total == 1
    with Session(sqlite_engine) as session:
        portal = session.scalar(select(Portal))
        assert portal is not None
        assert portal.scan_enabled is False


# ---------------------------------------------------------------------------
# 11: realistic multi-source fixture
# ---------------------------------------------------------------------------


def test_realistic_multi_source_fixture(
    sqlite_engine: Engine, tmp_path: Path
) -> None:
    """Synthetic SpaceX/Discord-style multi-source employer is fully represented."""

    _seed_cluster(sqlite_engine, "CG-SX", "SpaceX")
    _seed_cluster(sqlite_engine, "CG-DC", "Discord")
    _seed_cluster(sqlite_engine, "CG-CO", "Coalition")
    registry = _write_registry(
        tmp_path / "reg.csv",
        [
            # SpaceX main + international
            _row("SpaceX", "CG-SX", source_key="spacex_main",
                 operational="https://boards-api.greenhouse.io/v1/boards/spacex/jobs?content=true",
                 cohort="CORE_EXTENSION"),
            _row("SpaceX", "CG-SX", source_key="spacex_international",
                 operational="https://boards-api.greenhouse.io/v1/boards/spacexglobal/jobs?content=true",
                 cohort="CORE_EXTENSION"),
            # Discord main + international
            _row("Discord", "CG-DC", source_key="discord_main",
                 operational="https://boards-api.greenhouse.io/v1/boards/discord/jobs?content=true",
                 cohort="CORE_EXTENSION"),
            _row("Discord", "CG-DC", source_key="discord_international",
                 operational="https://boards-api.greenhouse.io/v1/boards/discordinternational/jobs?content=true",
                 cohort="CORE_EXTENSION"),
            # Coalition regional boards
            _row("Coalition", "CG-CO", source_key="coalition_us",
                 operational="https://boards-api.greenhouse.io/v1/boards/coalition/jobs?content=true",
                 cohort="CORE_EXTENSION"),
            _row("Coalition", "CG-CO", source_key="coalition_uk",
                 operational="https://boards-api.greenhouse.io/v1/boards/coalitionuk/jobs?content=true",
                 cohort="CORE_EXTENSION"),
        ],
    )

    rows = read_registry(registry)
    cluster_mapping, _, _ = reconcile_clusters(sqlite_engine, rows)
    report = sync_operational_sources(
        sqlite_engine, registry, cluster_mapping=cluster_mapping
    )

    # All 6 rows reconcile (4 employers) with no auto fuzzy matching.
    assert report.unmatched_employers == ()
    assert set(report.matched_employers) == {"SpaceX", "Discord", "Coalition"}
    assert set(report.multi_source_employers) == {"SpaceX", "Discord", "Coalition"}
    # 6 distinct operational URLs -> 6 portals.
    assert report.created_portals == 6
    assert report.created_mappings == 6
    with Session(sqlite_engine) as session:
        for cluster_id in ("CG-SX", "CG-DC", "CG-CO"):
            count = session.scalar(
                select(ClusterPortalMapping).where(
                    ClusterPortalMapping.corporate_cluster_id == cluster_id
                )
            )
            assert count is not None
            mappings = session.scalars(
                select(ClusterPortalMapping).where(
                    ClusterPortalMapping.corporate_cluster_id == cluster_id
                )
            ).all()
            assert len(mappings) == 2


# ---------------------------------------------------------------------------
# 12: SourceJob and JobAiAnalysis remain untouched
# ---------------------------------------------------------------------------


def test_sync_does_not_touch_source_jobs_or_ai_analyses(
    sqlite_engine: Engine, tmp_path: Path
) -> None:
    _seed_cluster(sqlite_engine, "CG-12", "KeepMyJobs")
    # Pre-populate a SourceJob + JobAiAnalysis to ensure they are not
    # deleted or modified by the sync.
    from research_agent.db.models import JobAiAnalysis, ScanRun, SourceJob
    with Session(sqlite_engine) as session, session.begin():
        from research_agent.db.models import ImportBatch as _IB
        batch = _IB(
            source_kind="test_fixture",
            source_filename="fixture.csv",
            source_path="/tmp/fixture.csv",
            source_sha256="fixture-source-job-12",
            source_version="fixture-v1",
            status="COMPLETED",
        )
        session.add(batch)
        session.flush()
        scan = ScanRun(
            source="fixture",
            status="COMPLETED",
            portal_count=0,
            success_count=0,
            failure_count=0,
            request_count=0,
            retry_count=0,
            http_2xx_count=0,
            http_3xx_count=0,
            http_4xx_count=0,
            http_5xx_count=0,
            http_429_count=0,
            jobs_discovered=1,
            new_jobs=1,
            updated_jobs=0,
            duplicates=0,
            jobs_closed=0,
            pipeline_status="NOT_PROCESSED",
        )
        session.add(scan)
        session.flush()
        sj = SourceJob(
            scan_run_id=scan.id,
            portal_id=None,
            source="fixture",
            source_job_id="fixture-job-1",
            source_url="https://fixture.example/job-1",
            apply_url="https://fixture.example/job-1",
            canonical_apply_url="https://fixture.example/job-1",
            raw_title="Fixture Cyber Engineer",
            resolved_corporate_cluster_id="CG-12",
            resolved_company_name="KeepMyJobs",
            payload_sha256="x" * 64,
            adapter="fixture-adapter",
            parser_version="fixture-parser-v1",
            ai_status="PENDING_AI",
        )
        session.add(sj)
        session.flush()
        analysis = JobAiAnalysis(
            source_job_row_id=sj.id,
            model="fixture-model",
            prompt_version="cyber-job-v4",
            schema_version="job-analysis-v1",
            input_payload_sha256="x" * 64,
            is_cybersecurity=True,
            needs_more_detail=False,
            valid=True,
            analysis_json=json.dumps({"fixture": True}),
        )
        session.add(analysis)
        session.flush()
        sj_id = sj.id
        analysis_id = analysis.id
    # Now run the sync.
    registry = _write_registry(
        tmp_path / "reg.csv",
        [_row("KeepMyJobs", "CG-12", operational="https://boards-api.greenhouse.io/v1/boards/keepmyjobs/jobs?content=true")],
    )
    rows = read_registry(registry)
    cluster_mapping, _, _ = reconcile_clusters(sqlite_engine, rows)
    sync_operational_sources(sqlite_engine, registry, cluster_mapping=cluster_mapping)
    with Session(sqlite_engine) as session:
        sj_after = session.get(SourceJob, sj_id)
        analysis_after = session.get(JobAiAnalysis, analysis_id)
        assert sj_after is not None
        assert analysis_after is not None
        assert sj_after.raw_title == "Fixture Cyber Engineer"
        assert analysis_after.is_cybersecurity is True


# ---------------------------------------------------------------------------
# 13: dry-run matches real sync shape
# ---------------------------------------------------------------------------


def test_dry_run_reports_matching_counts(
    sqlite_engine: Engine, tmp_path: Path
) -> None:
    _seed_cluster(sqlite_engine, "CG-13", "DryRun")
    registry = _write_registry(
        tmp_path / "reg.csv",
        [
            _row("DryRun", "CG-13", source_key="a", operational="https://boards-api.greenhouse.io/v1/boards/dryrun/jobs?content=true"),
            _row("DryRun", "CG-13", source_key="b", operational="https://boards-api.greenhouse.io/v1/boards/dryrunintl/jobs?content=true"),
        ],
    )
    rows = read_registry(registry)
    cluster_mapping, _, _ = reconcile_clusters(sqlite_engine, rows)
    dry = dry_run_sync(sqlite_engine, rows, cluster_mapping)
    assert dry.would_create_portals == 2
    assert dry.would_create_mappings == 2
    assert dry.matched_employers == ("DryRun",)
    assert dry.multi_source_employers == ("DryRun",)
    # After running the real sync, repeat dry-run -> all reused, 0 created.
    sync_operational_sources(sqlite_engine, registry, cluster_mapping=cluster_mapping)
    second = dry_run_sync(sqlite_engine, rows, cluster_mapping)
    assert second.would_create_portals == 0
    assert second.would_reuse_portals == 2
    assert second.would_create_mappings == 0
    assert second.would_update_mappings == 2
