"""Strict, idempotent import of the authoritative company master."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import distinct, func, insert, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_agent.company.portal_registry import build_portal_registry
from research_agent.db.migrations import create_schema
from research_agent.db.models import (
    ClusterPortalMapping,
    CompanyRecord,
    CorporateCluster,
    ImportBatch,
    Portal,
    utc_now,
)

MASTER_HEADERS = (
    "Record ID",
    "Employer",
    "Canonical Employer",
    "Parent Group",
    "Corporate Cluster ID",
    "Canonical Name Occurrences",
    "Duplicate Review Flag",
    "Entity Class",
    "Career Scan Eligible",
    "Sector",
    "Discovery Geography",
    "Org Type",
    "Corporate Website",
    "Website Status",
    "Careers URL",
    "Career Scan Status",
    "Discovery Source",
    "Source URL",
    "Notes",
    "Freeze Version",
    "Freeze Status",
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
)

REQUIRED_RESOLVED_FIELDS = (
    "Resolved Corporate Website",
    "Resolved Careers Landing URL",
    "Resolved Jobs Search URL",
    "ATS Family",
    "ATS Confidence",
    "Portal Verification URL",
    "Portal Verified Date",
    "Resolution Wave",
)


class MasterImportError(ValueError):
    pass


@dataclass(frozen=True)
class MasterMetrics:
    master_rows: int
    unique_record_ids: int
    corporate_clusters: int
    resolved_rows: int
    resolved_clusters: int
    unique_resolved_jobs_urls: int
    cluster_portal_mappings: int


@dataclass(frozen=True)
class ImportResult:
    import_batch_id: int
    source_sha256: str
    already_imported: bool
    metrics: MasterMetrics


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_master(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise MasterImportError(f"Master file not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        actual_headers = tuple(reader.fieldnames or ())
        if actual_headers != MASTER_HEADERS:
            raise MasterImportError(
                "Unexpected master schema. "
                f"Expected {list(MASTER_HEADERS)}, got {list(actual_headers)}"
            )
        rows = list(reader)

    malformed = [index for index, row in enumerate(rows, start=2) if None in row]
    if malformed:
        raise MasterImportError(f"Malformed CSV rows: {malformed[:10]}")
    _validate_rows(rows)
    return rows


def _validate_rows(rows: list[dict[str, str]]) -> None:
    record_ids = [row["Record ID"].strip() for row in rows]
    blank_record_rows = [index for index, value in enumerate(record_ids, start=2) if not value]
    if blank_record_rows:
        raise MasterImportError(f"Blank Record ID at rows {blank_record_rows[:10]}")
    duplicates = sorted(value for value, count in Counter(record_ids).items() if count > 1)
    if duplicates:
        raise MasterImportError(f"Duplicate Record ID values: {duplicates[:10]}")

    blank_clusters = [
        index for index, row in enumerate(rows, start=2) if not row["Corporate Cluster ID"].strip()
    ]
    if blank_clusters:
        raise MasterImportError(f"Blank Corporate Cluster ID at rows {blank_clusters[:10]}")

    for index, row in enumerate(rows, start=2):
        wave = row["Resolution Wave"].strip()
        status = row["Portal Resolution Status"].strip()
        if wave:
            missing = [field for field in REQUIRED_RESOLVED_FIELDS if not row[field].strip()]
            if missing:
                raise MasterImportError(f"Resolved row {index} is missing {missing}")
            if not status.startswith("VERIFIED"):
                raise MasterImportError(f"Resolved row {index} has non-verified status {status!r}")
        elif row["Resolved Jobs Search URL"].strip():
            raise MasterImportError(f"Unresolved row {index} unexpectedly has a Jobs Search URL")
        _parse_optional_date(row["Portal Verified Date"], row_number=index)
        _parse_optional_int(row["Canonical Name Occurrences"], row_number=index)


def _parse_optional_date(value: str, *, row_number: int | None = None) -> date | None:
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return date.fromisoformat(stripped)
    except ValueError as exc:
        suffix = f" at row {row_number}" if row_number else ""
        raise MasterImportError(f"Invalid ISO date {value!r}{suffix}") from exc


def _parse_optional_int(value: str, *, row_number: int | None = None) -> int | None:
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return int(stripped)
    except ValueError as exc:
        suffix = f" at row {row_number}" if row_number else ""
        raise MasterImportError(f"Invalid integer {value!r}{suffix}") from exc


def _json_values(rows: list[dict[str, str]], field: str) -> str:
    values = sorted({row[field].strip() for row in rows if row[field].strip()}, key=str.casefold)
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


def _representative_name(rows: list[dict[str, str]]) -> str:
    values = [
        row["Canonical Employer"].strip() for row in rows if row["Canonical Employer"].strip()
    ]
    if not values:
        values = [row["Employer"].strip() for row in rows if row["Employer"].strip()]
    if not values:
        raise MasterImportError(
            f"Cluster {rows[0]['Corporate Cluster ID']} has no usable representative name"
        )
    counts = Counter(values)
    return sorted(counts, key=lambda value: (-counts[value], value.casefold(), value))[0]


def _cluster_payloads(rows: list[dict[str, str]], batch_id: int) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["Corporate Cluster ID"].strip()].append(row)

    payloads: list[dict[str, object]] = []
    for cluster_id, cluster_rows in sorted(grouped.items()):
        payloads.append(
            {
                "corporate_cluster_id": cluster_id,
                "representative_canonical_employer": _representative_name(cluster_rows),
                "canonical_employers_json": _json_values(cluster_rows, "Canonical Employer"),
                "parent_groups_json": _json_values(cluster_rows, "Parent Group"),
                "entity_classes_json": _json_values(cluster_rows, "Entity Class"),
                "eligibility_values_json": _json_values(cluster_rows, "Career Scan Eligible"),
                "sectors_json": _json_values(cluster_rows, "Sector"),
                "discovery_geographies_json": _json_values(cluster_rows, "Discovery Geography"),
                "org_types_json": _json_values(cluster_rows, "Org Type"),
                "record_count": len(cluster_rows),
                "has_primary_scan_eligibility": any(
                    row["Career Scan Eligible"].strip() == "Yes" for row in cluster_rows
                ),
                "active_in_master": True,
                "import_batch_id": batch_id,
            }
        )
    return payloads


def _record_payloads(rows: list[dict[str, str]], batch_id: int) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    field_map = {
        "Employer": "employer",
        "Canonical Employer": "canonical_employer",
        "Parent Group": "parent_group",
        "Corporate Cluster ID": "corporate_cluster_id",
        "Duplicate Review Flag": "duplicate_review_flag",
        "Entity Class": "entity_class",
        "Career Scan Eligible": "career_scan_eligible",
        "Sector": "sector",
        "Discovery Geography": "discovery_geography",
        "Org Type": "org_type",
        "Corporate Website": "corporate_website",
        "Website Status": "website_status",
        "Careers URL": "careers_url",
        "Career Scan Status": "career_scan_status",
        "Discovery Source": "discovery_source",
        "Source URL": "source_url",
        "Notes": "notes",
        "Freeze Version": "freeze_version",
        "Freeze Status": "freeze_status",
        "Resolved Corporate Website": "resolved_corporate_website",
        "Resolved Careers Landing URL": "resolved_careers_landing_url",
        "Resolved Jobs Search URL": "resolved_jobs_search_url",
        "Portal Scope": "portal_scope",
        "ATS Family": "ats_family",
        "ATS Confidence": "ats_confidence",
        "Portal Resolution Status": "portal_resolution_status",
        "Portal Verification URL": "portal_verification_url",
        "Resolution Parent Override": "resolution_parent_override",
        "Resolution Wave": "resolution_wave",
    }
    for row_number, row in enumerate(rows, start=2):
        payload: dict[str, object] = {
            "record_id": row["Record ID"].strip(),
            "source_row_number": row_number,
            "import_batch_id": batch_id,
            "canonical_name_occurrences": _parse_optional_int(
                row["Canonical Name Occurrences"], row_number=row_number
            ),
            "portal_verified_date": _parse_optional_date(
                row["Portal Verified Date"], row_number=row_number
            ),
            "raw_row_json": json.dumps(row, ensure_ascii=False, separators=(",", ":")),
        }
        payload.update({target: row[source].strip() for source, target in field_map.items()})
        payloads.append(payload)
    return payloads


def _metrics_from_rows(rows: list[dict[str, str]]) -> MasterMetrics:
    resolved = [row for row in rows if row["Resolution Wave"].strip()]
    registry = build_portal_registry(rows)
    return MasterMetrics(
        master_rows=len(rows),
        unique_record_ids=len({row["Record ID"].strip() for row in rows}),
        corporate_clusters=len({row["Corporate Cluster ID"].strip() for row in rows}),
        resolved_rows=len(resolved),
        resolved_clusters=len({row["Corporate Cluster ID"].strip() for row in resolved}),
        unique_resolved_jobs_urls=len(registry.portals),
        cluster_portal_mappings=len(registry.mappings),
    )


def database_metrics(session: Session) -> MasterMetrics:
    master_rows = session.scalar(select(func.count()).select_from(CompanyRecord)) or 0
    unique_record_ids = session.scalar(select(func.count(distinct(CompanyRecord.record_id)))) or 0
    corporate_clusters = session.scalar(select(func.count()).select_from(CorporateCluster)) or 0
    resolved_rows = (
        session.scalar(
            select(func.count())
            .select_from(CompanyRecord)
            .where(CompanyRecord.resolution_wave != "")
        )
        or 0
    )
    resolved_clusters = (
        session.scalar(select(func.count(distinct(ClusterPortalMapping.corporate_cluster_id)))) or 0
    )
    unique_resolved_jobs_urls = (
        session.scalar(
            select(func.count()).select_from(Portal).where(Portal.active_in_registry.is_(True))
        )
        or 0
    )
    cluster_portal_mappings = (
        session.scalar(select(func.count()).select_from(ClusterPortalMapping)) or 0
    )
    return MasterMetrics(
        master_rows=master_rows,
        unique_record_ids=unique_record_ids,
        corporate_clusters=corporate_clusters,
        resolved_rows=resolved_rows,
        resolved_clusters=resolved_clusters,
        unique_resolved_jobs_urls=unique_resolved_jobs_urls,
        cluster_portal_mappings=cluster_portal_mappings,
    )


def import_master(
    engine: Engine, path: Path, *, source_version: str = "v1.5-wave5"
) -> ImportResult:
    create_schema(engine)
    resolved_path = path.expanduser().resolve()
    source_sha = file_sha256(resolved_path)
    rows = read_master(resolved_path)
    expected_metrics = _metrics_from_rows(rows)

    with Session(engine) as session, session.begin():
        existing_batch = session.scalar(
            select(ImportBatch).where(ImportBatch.source_sha256 == source_sha)
        )
        if existing_batch is not None:
            if existing_batch.status != "COMPLETED":
                raise MasterImportError(
                    f"Import batch {existing_batch.id} exists with status {existing_batch.status}"
                )
            return ImportResult(
                import_batch_id=existing_batch.id,
                source_sha256=source_sha,
                already_imported=True,
                metrics=database_metrics(session),
            )

        existing_rows = session.scalar(select(func.count()).select_from(CompanyRecord)) or 0
        if existing_rows:
            raise MasterImportError(
                "A different authoritative master is already loaded. "
                "Refusing a silent replacement; use a versioned migration/import workflow."
            )

        batch = ImportBatch(
            source_kind="authoritative_company_master",
            source_filename=resolved_path.name,
            source_path=str(resolved_path),
            source_sha256=source_sha,
            source_version=source_version,
            status="RUNNING",
        )
        session.add(batch)
        session.flush()

        cluster_payloads = _cluster_payloads(rows, batch.id)
        session.execute(insert(CorporateCluster), cluster_payloads)
        session.execute(insert(CompanyRecord), _record_payloads(rows, batch.id))

        registry = build_portal_registry(rows)
        portal_payloads = [
            {
                "normalized_jobs_url": item.normalized_jobs_url,
                "jobs_search_url": item.jobs_search_url,
                "scheme": item.scheme,
                "host": item.host,
                "ats_families_json": json.dumps(
                    item.ats_families, ensure_ascii=False, separators=(",", ":")
                ),
                "ats_confidences_json": json.dumps(
                    item.ats_confidences, ensure_ascii=False, separators=(",", ":")
                ),
                "metadata_conflict": item.metadata_conflict,
                "cluster_count": len(item.cluster_ids),
                "active_in_registry": True,
                "health_state": "UNKNOWN",
                "consecutive_failures": 0,
                "import_batch_id": batch.id,
            }
            for item in registry.portals
        ]
        session.execute(insert(Portal), portal_payloads)
        portal_ids = dict(session.execute(select(Portal.normalized_jobs_url, Portal.id)).all())

        mapping_payloads = [
            {
                "corporate_cluster_id": item.corporate_cluster_id,
                "portal_id": portal_ids[item.normalized_jobs_url],
                "resolved_corporate_website": item.resolved_corporate_website,
                "resolved_careers_landing_url": item.resolved_careers_landing_url,
                "source_jobs_search_url": item.source_jobs_search_url,
                "portal_scope": item.portal_scope,
                "ats_family": item.ats_family,
                "ats_confidence": item.ats_confidence,
                "portal_resolution_status": item.portal_resolution_status,
                "portal_verification_url": item.portal_verification_url,
                "portal_verified_date": _parse_optional_date(item.portal_verified_date),
                "resolution_parent_override": item.resolution_parent_override,
                "resolution_wave": item.resolution_wave,
                "source_record_count": item.source_record_count,
                "import_batch_id": batch.id,
            }
            for item in registry.mappings
        ]
        session.execute(insert(ClusterPortalMapping), mapping_payloads)

        actual_metrics = database_metrics(session)
        if actual_metrics != expected_metrics:
            raise MasterImportError(
                f"Database metrics diverged during import: {actual_metrics} != {expected_metrics}"
            )

        batch.status = "COMPLETED"
        batch.finished_at = utc_now()
        batch.row_count = actual_metrics.master_rows
        batch.cluster_count = actual_metrics.corporate_clusters
        batch.resolved_row_count = actual_metrics.resolved_rows
        batch.resolved_cluster_count = actual_metrics.resolved_clusters
        batch.portal_count = actual_metrics.unique_resolved_jobs_urls
        batch.validation_json = json.dumps(asdict(actual_metrics), sort_keys=True)

        return ImportResult(
            import_batch_id=batch.id,
            source_sha256=source_sha,
            already_imported=False,
            metrics=actual_metrics,
        )
