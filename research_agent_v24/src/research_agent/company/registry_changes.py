"""Versioned, auditable Portal Registry corrections and wave synchronization."""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_agent.company.importer import (
    MASTER_HEADERS,
    MasterMetrics,
    database_metrics,
    file_sha256,
)
from research_agent.company.portal_registry import normalize_jobs_url
from research_agent.db.migrations import create_schema
from research_agent.db.models import (
    ClusterPortalMapping,
    CompanyRecord,
    CorporateCluster,
    ImportBatch,
    Portal,
    RegistryChangeAudit,
    utc_now,
)

CHANGE_HEADERS = (
    "Action",
    "Corporate Cluster ID",
    "Old Jobs Search URL",
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
    "Reason",
)

_NEW_REQUIRED = (
    "Resolved Corporate Website",
    "Resolved Careers Landing URL",
    "Resolved Jobs Search URL",
    "Portal Scope",
    "ATS Family",
    "ATS Confidence",
    "Portal Resolution Status",
    "Resolution Wave",
)

_RECORD_FIELD_MAP = {
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


@dataclass(frozen=True)
class RegistryChangeResult:
    import_batch_id: int
    source_sha256: str
    already_applied: bool
    action_counts: dict[str, int]
    before_metrics: MasterMetrics
    after_metrics: MasterMetrics


class RegistryChangeError(ValueError):
    pass


def read_registry_changes(path: Path) -> list[dict[str, str]]:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise RegistryChangeError(f"Registry change file not found: {resolved}")
    with resolved.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        actual = tuple(reader.fieldnames or ())
        if actual != CHANGE_HEADERS:
            raise RegistryChangeError(
                "Unexpected registry change schema. "
                f"Expected {list(CHANGE_HEADERS)}, got {list(actual)}"
            )
        rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
    if not rows:
        raise RegistryChangeError("Registry change file is empty")
    _validate_change_rows(rows)
    return rows


def _validate_change_rows(rows: list[dict[str, str]]) -> None:
    clusters = [row["Corporate Cluster ID"] for row in rows]
    duplicates = sorted(value for value, count in Counter(clusters).items() if count > 1)
    if duplicates:
        raise RegistryChangeError(f"Duplicate cluster changes: {duplicates[:10]}")
    for index, row in enumerate(rows, start=2):
        action = row["Action"].upper()
        if action not in {"ADD", "UPDATE", "RETIRE", "SUSPEND", "RESUME"}:
            raise RegistryChangeError(f"Row {index} has invalid action {row['Action']!r}")
        if not row["Corporate Cluster ID"]:
            raise RegistryChangeError(f"Row {index} has a blank Corporate Cluster ID")
        for field in ("Portal Verification URL", "Portal Verified Date", "Reason"):
            if not row[field]:
                raise RegistryChangeError(f"Row {index} is missing {field}")
        _validate_public_url(row["Portal Verification URL"], row=index, field="evidence URL")
        _parse_date(row["Portal Verified Date"], row=index)
        if action in {"UPDATE", "RETIRE", "SUSPEND", "RESUME"}:
            if not row["Old Jobs Search URL"]:
                raise RegistryChangeError(f"Row {index} requires Old Jobs Search URL")
            normalize_jobs_url(row["Old Jobs Search URL"])
        elif row["Old Jobs Search URL"]:
            raise RegistryChangeError(f"Row {index} ADD must not provide Old Jobs Search URL")
        if action in {"ADD", "UPDATE"}:
            missing = [field for field in _NEW_REQUIRED if not row[field]]
            if missing:
                raise RegistryChangeError(f"Row {index} is missing {missing}")
            for field in (
                "Resolved Corporate Website",
                "Resolved Careers Landing URL",
                "Resolved Jobs Search URL",
            ):
                _validate_public_url(row[field], row=index, field=field)
            normalize_jobs_url(row["Resolved Jobs Search URL"])
            if not row["Portal Resolution Status"].startswith("VERIFIED"):
                raise RegistryChangeError(
                    f"Row {index} has non-verified status {row['Portal Resolution Status']!r}"
                )
        else:
            forbidden = [field for field in _NEW_REQUIRED if row[field]]
            if forbidden:
                raise RegistryChangeError(
                    f"Row {index} RETIRE unexpectedly supplies replacement fields {forbidden}"
                )


def apply_registry_changes(
    engine: Engine,
    path: Path,
    *,
    source_version: str,
) -> RegistryChangeResult:
    create_schema(engine)
    resolved = path.expanduser().resolve()
    rows = read_registry_changes(resolved)
    source_sha = file_sha256(resolved)

    with Session(engine) as session, session.begin():
        existing = session.scalar(
            select(ImportBatch).where(ImportBatch.source_sha256 == source_sha)
        )
        if existing is not None:
            if existing.source_kind != "registry_change" or existing.status != "COMPLETED":
                raise RegistryChangeError(
                    f"Checksum belongs to incompatible import batch {existing.id}"
                )
            audits = session.scalars(
                select(RegistryChangeAudit).where(
                    RegistryChangeAudit.import_batch_id == existing.id
                )
            ).all()
            metrics = database_metrics(session)
            validation = json.loads(existing.validation_json or "{}")
            before = MasterMetrics(**validation.get("before", asdict(metrics)))
            after = MasterMetrics(**validation.get("after", asdict(metrics)))
            return RegistryChangeResult(
                import_batch_id=existing.id,
                source_sha256=source_sha,
                already_applied=True,
                action_counts=dict(Counter(audit.action for audit in audits)),
                before_metrics=before,
                after_metrics=after,
            )

        before_metrics = database_metrics(session)
        batch = ImportBatch(
            source_kind="registry_change",
            source_filename=resolved.name,
            source_path=str(resolved),
            source_sha256=source_sha,
            source_version=source_version,
            status="RUNNING",
        )
        session.add(batch)
        session.flush()

        for row in rows:
            _apply_change(session, batch.id, row)

        after_metrics = database_metrics(session)
        batch.status = "COMPLETED"
        batch.finished_at = utc_now()
        batch.row_count = after_metrics.master_rows
        batch.cluster_count = after_metrics.corporate_clusters
        batch.resolved_row_count = after_metrics.resolved_rows
        batch.resolved_cluster_count = after_metrics.resolved_clusters
        batch.portal_count = after_metrics.unique_resolved_jobs_urls
        batch.validation_json = json.dumps(
            {
                "action_counts": dict(Counter(row["Action"].upper() for row in rows)),
                "before": asdict(before_metrics),
                "after": asdict(after_metrics),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return RegistryChangeResult(
            import_batch_id=batch.id,
            source_sha256=source_sha,
            already_applied=False,
            action_counts=dict(Counter(row["Action"].upper() for row in rows)),
            before_metrics=before_metrics,
            after_metrics=after_metrics,
        )


def _apply_change(session: Session, batch_id: int, row: dict[str, str]) -> None:
    cluster_id = row["Corporate Cluster ID"]
    cluster = session.get(CorporateCluster, cluster_id)
    if cluster is None:
        raise RegistryChangeError(f"Unknown Corporate Cluster ID {cluster_id}")
    mappings = session.scalars(
        select(ClusterPortalMapping).where(
            ClusterPortalMapping.corporate_cluster_id == cluster_id
        )
    ).all()
    if len(mappings) > 1:
        raise RegistryChangeError(f"Cluster {cluster_id} has multiple current portal mappings")
    mapping = mappings[0] if mappings else None
    action = row["Action"].upper()
    if action == "ADD" and mapping is not None:
        raise RegistryChangeError(f"ADD cluster {cluster_id} is already resolved")
    if action in {"UPDATE", "RETIRE", "SUSPEND", "RESUME"} and mapping is None:
        raise RegistryChangeError(f"{action} cluster {cluster_id} has no current mapping")

    before = _mapping_snapshot(mapping)
    if mapping is not None:
        actual_old = normalize_jobs_url(mapping.source_jobs_search_url)
        expected_old = normalize_jobs_url(row["Old Jobs Search URL"])
        if actual_old != expected_old:
            raise RegistryChangeError(
                f"Cluster {cluster_id} old URL mismatch: {expected_old} != {actual_old}"
            )
    affected_portal_ids = {mapping.portal_id} if mapping is not None else set()

    if action == "RETIRE":
        if mapping is not None:
            session.delete(mapping)
        _update_company_records(session, cluster_id, None)
        after: dict[str, object] = {}
    elif action in {"SUSPEND", "RESUME"}:
        if mapping is None:
            raise RegistryChangeError(f"{action} cluster {cluster_id} has no current mapping")
        portal = session.get(Portal, mapping.portal_id)
        if portal is None:
            raise RegistryChangeError(f"Cluster {cluster_id} references a missing portal")
        portal.scan_enabled = action == "RESUME"
        portal.access_state = "AVAILABLE" if action == "RESUME" else _access_state(row["Reason"])
        if action == "RESUME":
            portal.cooldown_until = None
            portal.last_block_reason = None
        else:
            portal.last_block_reason = row["Reason"]
        after = _mapping_snapshot(mapping)
        after.update(
            {
                "scan_enabled": portal.scan_enabled,
                "access_state": portal.access_state,
            }
        )
    else:
        portal = _get_or_create_portal(session, batch_id, row)
        affected_portal_ids.add(portal.id)
        if mapping is None:
            mapping = ClusterPortalMapping(
                corporate_cluster_id=cluster_id,
                portal_id=portal.id,
                resolved_corporate_website="",
                resolved_careers_landing_url="",
                source_jobs_search_url="",
                portal_scope="",
                ats_family="",
                ats_confidence="",
                portal_resolution_status="",
                portal_verification_url="",
                portal_verified_date=_parse_date(row["Portal Verified Date"]),
                resolution_parent_override="",
                resolution_wave="",
                source_record_count=0,
                import_batch_id=batch_id,
            )
            session.add(mapping)
        mapping.portal_id = portal.id
        mapping.resolved_corporate_website = row["Resolved Corporate Website"]
        mapping.resolved_careers_landing_url = row["Resolved Careers Landing URL"]
        mapping.source_jobs_search_url = row["Resolved Jobs Search URL"]
        mapping.portal_scope = row["Portal Scope"]
        mapping.ats_family = row["ATS Family"]
        mapping.ats_confidence = row["ATS Confidence"]
        mapping.portal_resolution_status = row["Portal Resolution Status"]
        mapping.portal_verification_url = row["Portal Verification URL"]
        mapping.portal_verified_date = _parse_date(row["Portal Verified Date"])
        mapping.resolution_parent_override = row["Resolution Parent Override"]
        mapping.resolution_wave = row["Resolution Wave"]
        mapping.source_record_count = (
            session.scalar(
                select(func.count())
                .select_from(CompanyRecord)
                .where(CompanyRecord.corporate_cluster_id == cluster_id)
            )
            or 0
        )
        mapping.import_batch_id = batch_id
        _update_company_records(session, cluster_id, row)
        session.flush()
        after = _mapping_snapshot(mapping)

    session.flush()
    for portal_id in affected_portal_ids:
        _refresh_portal_aggregate(session, portal_id)
    session.add(
        RegistryChangeAudit(
            import_batch_id=batch_id,
            corporate_cluster_id=cluster_id,
            action=action,
            reason=row["Reason"],
            evidence_url=row["Portal Verification URL"],
            verified_date=_parse_date(row["Portal Verified Date"]),
            before_json=json.dumps(before, ensure_ascii=False, sort_keys=True),
            after_json=json.dumps(after, ensure_ascii=False, sort_keys=True),
        )
    )


def _get_or_create_portal(session: Session, batch_id: int, row: dict[str, str]) -> Portal:
    normalized = normalize_jobs_url(row["Resolved Jobs Search URL"])
    portal = session.scalar(select(Portal).where(Portal.normalized_jobs_url == normalized))
    if portal is not None:
        portal.active_in_registry = True
        return portal
    parsed = urlsplit(normalized)
    portal = Portal(
        normalized_jobs_url=normalized,
        jobs_search_url=row["Resolved Jobs Search URL"],
        scheme=parsed.scheme,
        host=parsed.hostname or "",
        ats_families_json=json.dumps([row["ATS Family"]], separators=(",", ":")),
        ats_confidences_json=json.dumps([row["ATS Confidence"]], separators=(",", ":")),
        metadata_conflict=False,
        cluster_count=0,
        active_in_registry=True,
        scan_enabled=True,
        access_state="AVAILABLE",
        health_state="UNKNOWN",
        consecutive_failures=0,
        import_batch_id=batch_id,
    )
    session.add(portal)
    session.flush()
    return portal


def _refresh_portal_aggregate(session: Session, portal_id: int) -> None:
    portal = session.get(Portal, portal_id)
    if portal is None:
        return
    mappings = session.scalars(
        select(ClusterPortalMapping).where(ClusterPortalMapping.portal_id == portal_id)
    ).all()
    portal.cluster_count = len(mappings)
    portal.active_in_registry = bool(mappings)
    if not mappings:
        portal.scan_enabled = False
        portal.access_state = "RETIRED"
        return
    families = sorted({mapping.ats_family for mapping in mappings})
    confidences = sorted({mapping.ats_confidence for mapping in mappings})
    portal.ats_families_json = json.dumps(families, ensure_ascii=False, separators=(",", ":"))
    portal.ats_confidences_json = json.dumps(
        confidences, ensure_ascii=False, separators=(",", ":")
    )
    portal.metadata_conflict = len(families) > 1 or len(confidences) > 1
    portal.jobs_search_url = sorted(
        {mapping.source_jobs_search_url for mapping in mappings}, key=str.casefold
    )[0]


def _update_company_records(
    session: Session, cluster_id: str, row: dict[str, str] | None
) -> None:
    records = session.scalars(
        select(CompanyRecord).where(CompanyRecord.corporate_cluster_id == cluster_id)
    ).all()
    for record in records:
        for source, target in _RECORD_FIELD_MAP.items():
            setattr(record, target, row[source] if row is not None else "")
        record.portal_verified_date = (
            _parse_date(row["Portal Verified Date"]) if row is not None else None
        )


def _mapping_snapshot(mapping: ClusterPortalMapping | None) -> dict[str, object]:
    if mapping is None:
        return {}
    return {
        "portal_id": mapping.portal_id,
        "resolved_corporate_website": mapping.resolved_corporate_website,
        "resolved_careers_landing_url": mapping.resolved_careers_landing_url,
        "source_jobs_search_url": mapping.source_jobs_search_url,
        "portal_scope": mapping.portal_scope,
        "ats_family": mapping.ats_family,
        "ats_confidence": mapping.ats_confidence,
        "portal_resolution_status": mapping.portal_resolution_status,
        "portal_verification_url": mapping.portal_verification_url,
        "portal_verified_date": mapping.portal_verified_date.isoformat(),
        "resolution_parent_override": mapping.resolution_parent_override,
        "resolution_wave": mapping.resolution_wave,
        "source_record_count": mapping.source_record_count,
    }


def export_synchronized_master(engine: Engine, destination: Path) -> Path:
    create_schema(engine)
    output = destination.expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite synchronized master: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with Session(engine) as session:
        records = session.scalars(
            select(CompanyRecord).order_by(CompanyRecord.source_row_number)
        ).all()
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MASTER_HEADERS)
        writer.writeheader()
        for record in records:
            row = json.loads(record.raw_row_json)
            for source, target in _RECORD_FIELD_MAP.items():
                row[source] = getattr(record, target)
            row["Portal Verified Date"] = (
                record.portal_verified_date.isoformat() if record.portal_verified_date else ""
            )
            writer.writerow({header: row.get(header, "") for header in MASTER_HEADERS})
    return output


def render_registry_change_report(result: RegistryChangeResult, source: Path) -> str:
    before = result.before_metrics
    after = result.after_metrics
    lines = [
        "# Registry change report",
        "",
        f"- Source: `{source.expanduser().resolve()}`",
        f"- SHA-256: `{result.source_sha256}`",
        f"- Import batch: `{result.import_batch_id}`",
        f"- Already applied: `{str(result.already_applied).lower()}`",
        "",
        "## Actions",
        "",
    ]
    lines.extend(f"- {action}: {count}" for action, count in sorted(result.action_counts.items()))
    lines.extend(
        [
            "",
            "## Metrics",
            "",
            "| Metric | Before | After | Delta |",
            "|---|---:|---:|---:|",
        ]
    )
    for field in MasterMetrics.__dataclass_fields__:
        old = getattr(before, field)
        new = getattr(after, field)
        lines.append(f"| `{field}` | {old:,} | {new:,} | {new - old:+,} |")
    return "\n".join(lines) + "\n"


def write_registry_change_json(result: RegistryChangeResult, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(
            asdict(result), ensure_ascii=False, indent=2, sort_keys=True, default=str
        )
        + "\n",
        encoding="utf-8",
    )


def _parse_date(value: str, *, row: int | None = None) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        suffix = f" at row {row}" if row is not None else ""
        raise RegistryChangeError(f"Invalid ISO date {value!r}{suffix}") from exc


def _validate_public_url(value: str, *, row: int, field: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise RegistryChangeError(f"Row {row} has invalid {field}: {value!r}")
    if parsed.username is not None or parsed.password is not None:
        raise RegistryChangeError(f"Row {row} has credentials in {field}")


def _access_state(reason: str) -> str:
    folded = reason.casefold()
    if "robots" in folded:
        return "ROBOTS_DENIED"
    if "captcha" in folded or "challenge" in folded:
        return "CHALLENGE"
    return "ACCESS_DENIED"
