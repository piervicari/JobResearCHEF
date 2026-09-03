import csv
import hashlib
import json
from pathlib import Path

from research_agent.config import PROJECT_ROOT

PORTAL_DIR = PROJECT_ROOT / "data" / "portal_resolution"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_delivered_assets_are_copied_without_modification() -> None:
    pairs = [
        (
            PROJECT_ROOT / "master_company_universe_v1_5_portal_resolution_wave5.csv",
            PROJECT_ROOT
            / "data"
            / "company_universe"
            / "master_company_universe_v1_5_portal_resolution_wave5.csv",
        ),
        *[
            (PROJECT_ROOT / name, PORTAL_DIR / name)
            for name in (
                "portal_resolution_wave5.csv",
                "portal_resolution_wave5_mapping_audit.csv",
                "portal_resolution_wave5_summary.json",
            )
        ],
    ]
    assert all(_sha256(source) == _sha256(copy) for source, copy in pairs)


def test_wave5_assets_are_mutually_consistent(master_path: Path) -> None:
    master = _read_csv(master_path)
    wave = _read_csv(PORTAL_DIR / "portal_resolution_wave5.csv")
    audit = _read_csv(PORTAL_DIR / "portal_resolution_wave5_mapping_audit.csv")
    summary = json.loads(
        (PORTAL_DIR / "portal_resolution_wave5_summary.json").read_text(encoding="utf-8-sig")
    )

    wave_clusters = {row["Corporate Cluster ID"] for row in wave}
    master_wave5 = [row for row in master if row["Resolution Wave"] == "W5"]
    assert len(wave) == 141
    assert len(wave_clusters) == 141
    assert len(master_wave5) == 142
    assert sum(int(row["Legal/Discovery Records Covered"]) for row in wave) == 142
    assert len(audit) == 141
    assert {row["Corporate Cluster ID"] for row in master_wave5} == wave_clusters
    assert summary["new_resolved_clusters"] == 141
    assert summary["new_master_records_covered"] == 142
    assert summary["cumulative_resolved_clusters"] == 575
    assert summary["cumulative_resolved_records"] == 1_263
