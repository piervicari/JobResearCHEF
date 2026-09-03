import csv
import hashlib
import json
import zipfile
from pathlib import Path

from research_agent.company.importer import MASTER_HEADERS
from research_agent.company.registry_changes import CHANGE_HEADERS
from research_agent.company.wave6 import AUDIT_HEADERS, REVIEW_HEADERS, WAVE_HEADERS
from research_agent.config import PROJECT_ROOT

PORTAL_DIR = PROJECT_ROOT / "data" / "portal_resolution"
MASTER_DIR = PROJECT_ROOT / "data" / "company_universe"


def test_wave6_assets_are_complete_consistent_and_conservative() -> None:
    selection = _read(PORTAL_DIR / "wave6_candidate_selection_v1.csv")
    reviewed = _read(PORTAL_DIR / "wave6_reviewed_resolutions_v1.csv")
    wave = _read(PORTAL_DIR / "portal_resolution_wave6.csv")
    audit = _read(PORTAL_DIR / "portal_resolution_wave6_mapping_audit.csv")
    registry = _read(PORTAL_DIR / "registry_wave6_v1.csv")
    summary = json.loads(
        (PORTAL_DIR / "portal_resolution_wave6_summary.json").read_text(encoding="utf-8")
    )

    assert len(selection) == len(wave) == len(audit) == 100
    assert len({row["corporate_cluster_id"] for row in selection}) == 100
    assert [int(row["rank"]) for row in selection] == list(range(1, 101))
    assert len(reviewed) == len(registry) == 15
    assert set(row["Corporate Cluster ID"] for row in reviewed) <= {
        row["corporate_cluster_id"] for row in selection
    }
    assert {row["Action"] for row in registry} == {"ADD"}
    assert tuple(registry[0]) == CHANGE_HEADERS
    assert tuple(reviewed[0]) == REVIEW_HEADERS
    assert tuple(wave[0]) == WAVE_HEADERS
    assert tuple(audit[0]) == AUDIT_HEADERS

    resolved = [row for row in wave if row["Resolution Outcome"] == "RESOLVED"]
    deferred = [row for row in wave if row["Resolution Outcome"] == "DEFERRED"]
    assert len(resolved) == 15
    assert len(deferred) == 85
    for row in resolved:
        assert all(
            row[field]
            for field in (
                "Corporate Website",
                "Careers Landing URL",
                "Jobs Search URL",
                "ATS Family",
                "Verification Evidence URL",
                "Verified Date",
            )
        )
        assert row["Deferral Reason"] == ""
    for row in deferred:
        assert row["Corporate Website"] == ""
        assert row["Careers Landing URL"] == ""
        assert row["Jobs Search URL"] == ""
        assert row["Deferral Reason"]
    assert {row["Audit Result"] for row in audit} == {"PASS"}
    assert summary["selected_clusters"] == 100
    assert summary["new_resolved_clusters"] == 15
    assert summary["deferred_clusters"] == 85
    assert summary["cumulative_resolved_clusters"] == 589
    assert summary["cumulative_resolved_records"] == 1_277
    assert all(summary["validation"].values())


def test_wave6_master_preserves_prior_rows_and_only_adds_reviewed_resolutions() -> None:
    prior_path = MASTER_DIR / "master_company_universe_v1_9_registry_corrections_run26.csv"
    current_path = MASTER_DIR / "master_company_universe_v1_10_portal_resolution_wave6.csv"
    prior = _read(prior_path)
    current = _read(current_path)
    assert tuple(current[0]) == MASTER_HEADERS
    assert len(prior) == len(current) == 12_503
    assert len({row["Record ID"] for row in current}) == 12_503

    prior_by_id = {row["Record ID"]: row for row in prior}
    resolution_fields = {
        "Resolved Corporate Website",
        "Resolved Careers Landing URL",
        "Resolved Jobs Search URL",
        "Portal Scope",
        "ATS Family",
        "ATS Confidence",
        "Portal Resolution Status",
        "Portal Verification URL",
        "Portal Verified Date",
        "Resolution Parent Override",
        "Resolution Wave",
    }
    wave6_rows = [row for row in current if row["Resolution Wave"] == "W6"]
    assert len(wave6_rows) == 15
    for row in current:
        before = prior_by_id[row["Record ID"]]
        for field in MASTER_HEADERS:
            if field not in resolution_fields:
                assert row[field] == before[field]
        if row["Resolution Wave"] != "W6":
            assert all(row[field] == before[field] for field in resolution_fields)


def test_wave6_distribution_contains_exact_versioned_artifacts() -> None:
    distribution = (
        PROJECT_ROOT / "data" / "distributions" / "portal_resolution_wave6_v1.zip"
    )
    expected = {
        "wave6_candidate_selection_v1.csv": PORTAL_DIR
        / "wave6_candidate_selection_v1.csv",
        "wave6_reviewed_resolutions_v1.csv": PORTAL_DIR
        / "wave6_reviewed_resolutions_v1.csv",
        "portal_resolution_wave6.csv": PORTAL_DIR / "portal_resolution_wave6.csv",
        "portal_resolution_wave6_mapping_audit.csv": PORTAL_DIR
        / "portal_resolution_wave6_mapping_audit.csv",
        "registry_wave6_v1.csv": PORTAL_DIR / "registry_wave6_v1.csv",
        "portal_resolution_wave6_summary.json": PORTAL_DIR
        / "portal_resolution_wave6_summary.json",
        "master_company_universe_v1_10_portal_resolution_wave6.csv": MASTER_DIR
        / "master_company_universe_v1_10_portal_resolution_wave6.csv",
    }
    with zipfile.ZipFile(distribution) as archive:
        assert set(archive.namelist()) == set(expected)
        for name, source in expected.items():
            assert hashlib.sha256(archive.read(name)).digest() == hashlib.sha256(
                source.read_bytes()
            ).digest()


def test_authoritative_v15_checksum_remains_immutable(master_path: Path) -> None:
    assert hashlib.sha256(master_path.read_bytes()).hexdigest() == (
        "bae44ad9ab0a5800bec884b43fc236506d9da3ea51f72477830e5023fa81e7df"
    )


def _read(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))
