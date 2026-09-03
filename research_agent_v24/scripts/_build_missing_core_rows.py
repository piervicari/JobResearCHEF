"""Generate the missing CORE_200 rows in tier_s_operational_sources_v1.csv.

This script is an offline generator. It reads `target_employers_v0_2.yaml`
(the authoritative 200-employer CORE_200 list) and emits one row per CORE
employer that is not already represented in the registry. Source-less rows
use empty `operational_url` and routing `HOLD`.

If a v0.2 employer has no `jobs_url`, we still emit a source-less row but
leave `canonical_careers_url` empty and tag the row for manual review.
The lead's invariants allow `canonical_careers_url` to be empty when no
operational source is known.

Output is written to stdout as CSV rows. The lead concatenates them with the
existing registry.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
YAML_PATH = ROOT / "data" / "target_employers" / "target_employers_v0_2.yaml"
REGISTRY_PATH = ROOT / "data" / "target_employers" / "tier_s_operational_sources_v1.csv"

REGISTRY_HEADERS = (
    "employer_name",
    "corporate_cluster_id",
    "priority",
    "cohort",
    "source_key",
    "source_scope",
    "canonical_careers_url",
    "operational_url",
    "ats_family",
    "evidence_state",
    "resolution_path",
    "adapter_supported",
    "catalog_state",
    "last_verified_at",
    "evidence_url",
    "notes",
    "scan_enabled",
    "routing_override",
    "routing_override_rationale",
)


def main() -> int:
    with YAML_PATH.open() as f:
        data = yaml.safe_load(f)
    v0_emps = data["employers"]
    with REGISTRY_PATH.open(encoding="utf-8-sig") as f:
        existing = list(csv.DictReader(f))
    existing_names = {r["employer_name"] for r in existing}
    missing = [e for e in v0_emps if e["name"] not in existing_names]
    if not missing:
        print("no missing rows", file=sys.stderr)
        return 0
    writer = csv.DictWriter(sys.stdout, fieldnames=REGISTRY_HEADERS)
    skipped_no_url = 0
    for emp in missing:
        cluster_id = emp.get("corporate_cluster_id") or ""
        priority = str(emp.get("portal_id") or "").strip() or "200"
        jobs_url = (emp.get("jobs_url") or "").strip()
        if not jobs_url:
            skipped_no_url += 1
        notes = (
            f"Source-less CORE_200 row. v0.2 first-party careers URL: {jobs_url!r}. "
            "No proven operational source yet; routing=HOLD until adapter + URL are identified."
        )
        row = {
            "employer_name": emp["name"],
            "corporate_cluster_id": cluster_id,
            "priority": priority,
            "cohort": "CORE_200",
            "source_key": f"{emp['name'].lower().replace(' ', '_')}_pending",
            "source_scope": "Global",
            "canonical_careers_url": jobs_url,
            "operational_url": "",
            "ats_family": "",
            "evidence_state": "UNVERIFIED",
            "resolution_path": "HOLD",
            "adapter_supported": "NO",
            "catalog_state": "UNTESTED",
            "last_verified_at": "",
            "evidence_url": jobs_url,
            "notes": notes,
            "scan_enabled": "N",
            "routing_override": "",
            "routing_override_rationale": "",
        }
        writer.writerow(row)
    print(
        f"generated {len(missing)} missing CORE_200 rows ({skipped_no_url} without v0.2 jobs_url)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
