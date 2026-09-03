"""Acceptance validation and reproducible Milestone 1 reporting."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_agent.company.importer import MasterMetrics, database_metrics, file_sha256
from research_agent.config import AcceptanceSettings
from research_agent.db.models import ImportBatch, Portal


@dataclass(frozen=True)
class AcceptanceCheck:
    metric: str
    expected: int
    actual: int
    passed: bool


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    checks: tuple[AcceptanceCheck, ...]
    database_metrics: MasterMetrics
    current_database_metrics: MasterMetrics
    portal_metadata_conflicts: int
    source_sha256: str
    source_checksum_valid: bool
    import_batch_id: int


def validate_database(
    engine: Engine,
    expected: AcceptanceSettings,
    source_path: Path | None = None,
) -> ValidationResult:
    with Session(engine) as session:
        current_metrics = database_metrics(session)
        batch = session.scalar(
            select(ImportBatch)
            .where(
                ImportBatch.status == "COMPLETED",
                ImportBatch.source_kind == "authoritative_company_master",
            )
            .order_by(ImportBatch.id.desc())
        )
        if batch is None:
            raise ValueError("No completed authoritative master import found")
        stored_validation = json.loads(batch.validation_json or "{}")
        try:
            metrics = MasterMetrics(**stored_validation)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Authoritative import batch {batch.id} has invalid validation evidence"
            ) from exc
        conflicts = (
            session.scalar(
                select(func.count()).select_from(Portal).where(Portal.metadata_conflict.is_(True))
            )
            or 0
        )

    expected_by_metric = {
        "master_rows": expected.rows,
        "unique_record_ids": expected.unique_record_ids,
        "corporate_clusters": expected.corporate_clusters,
        "resolved_rows": expected.resolved_rows,
        "resolved_clusters": expected.resolved_clusters,
        "unique_resolved_jobs_urls": expected.unique_resolved_jobs_urls,
    }
    actual_values = asdict(metrics)
    checks = tuple(
        AcceptanceCheck(
            metric=metric,
            expected=expected_value,
            actual=actual_values[metric],
            passed=actual_values[metric] == expected_value,
        )
        for metric, expected_value in expected_by_metric.items()
    )
    checksum_valid = source_path is None or file_sha256(source_path) == batch.source_sha256
    return ValidationResult(
        passed=all(check.passed for check in checks) and checksum_valid,
        checks=checks,
        database_metrics=metrics,
        current_database_metrics=current_metrics,
        portal_metadata_conflicts=conflicts,
        source_sha256=batch.source_sha256,
        source_checksum_valid=checksum_valid,
        import_batch_id=batch.id,
    )


def render_markdown_report(result: ValidationResult, source_path: Path) -> str:
    status = "PASS" if result.passed else "FAIL"
    rows = [
        "# Milestone 1 - Master v1.5 validation",
        "",
        f"**Overall result:** {status}",
        "",
        f"- Generated at (UTC): {datetime.now(UTC).isoformat()}",
        f"- Authoritative source: `{source_path}`",
        f"- Source SHA-256: `{result.source_sha256}`",
        f"- Source checksum matches import evidence: "
        f"`{'yes' if result.source_checksum_valid else 'no'}`",
        f"- Import batch ID: `{result.import_batch_id}`",
        "",
        "## Acceptance checks",
        "",
        "| Metric | Expected | Actual | Result |",
        "|---|---:|---:|:---:|",
    ]
    for check in result.checks:
        rows.append(
            f"| `{check.metric}` | {check.expected:,} | {check.actual:,} | "
            f"{'PASS' if check.passed else 'FAIL'} |"
        )
    rows.extend(
        [
            "",
            "## Authoritative import snapshot",
            "",
            f"- Cluster-to-portal mappings: {result.database_metrics.cluster_portal_mappings:,}",
            f"- Deduplicated operational portals: "
            f"{result.database_metrics.unique_resolved_jobs_urls:,}",
            f"- Portals with cluster-specific ATS metadata variants: "
            f"{result.portal_metadata_conflicts:,}",
            "- URL normalization preserves paths and query strings and removes only safe "
            "syntax noise.",
            "- Company-specific portal metadata remains on the cluster-to-portal mapping.",
            "- Later versioned corrections may change current resolved/portal counts without "
            "mutating this historical acceptance snapshot.",
            "",
            "## Current synchronized state",
            "",
            f"- Resolved rows: {result.current_database_metrics.resolved_rows:,}",
            f"- Resolved clusters: {result.current_database_metrics.resolved_clusters:,}",
            f"- Active registry portals: "
            f"{result.current_database_metrics.unique_resolved_jobs_urls:,}",
            "",
            "## Gate",
            "",
            (
                "All Milestone 1 acceptance criteria passed. Scanner implementation may proceed; "
                "full-registry scanning remains a separate explicit opt-in and is not validated "
                "by this report."
                if result.passed
                else "Scanner implementation must not proceed until all failed checks are resolved."
            ),
            "",
        ]
    )
    return "\n".join(rows)


def write_json_report(result: ValidationResult, path: Path) -> None:
    payload = {
        "passed": result.passed,
        "checks": [asdict(check) for check in result.checks],
        "database_metrics": asdict(result.database_metrics),
        "current_database_metrics": asdict(result.current_database_metrics),
        "portal_metadata_conflicts": result.portal_metadata_conflicts,
        "source_sha256": result.source_sha256,
        "source_checksum_valid": result.source_checksum_valid,
        "import_batch_id": result.import_batch_id,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify_source_checksum(source_path: Path, expected_sha256: str) -> bool:
    return file_sha256(source_path) == expected_sha256
