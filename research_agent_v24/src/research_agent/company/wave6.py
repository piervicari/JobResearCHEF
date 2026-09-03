"""Deterministic, review-first prioritization for Portal Resolution Wave 6."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_agent.config import PROJECT_ROOT
from research_agent.db.models import ClusterPortalMapping, CorporateCluster

REVIEW_HEADERS = (
    "Corporate Cluster ID",
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
WAVE_HEADERS = (
    "Corporate Cluster ID",
    "Selection Rank",
    "Priority Score",
    "Representative Employer",
    "Legal/Discovery Records Covered",
    "Resolution Outcome",
    "Corporate Website",
    "Careers Landing URL",
    "Jobs Search URL",
    "Portal Scope",
    "ATS Family",
    "ATS Confidence",
    "Resolution Status",
    "Verification Evidence URL",
    "Verified Date",
    "Parent Override",
    "Deferral Reason",
    "Notes",
)
AUDIT_HEADERS = (
    "Corporate Cluster ID",
    "Selection Rank",
    "Representative Employer",
    "Resolution Outcome",
    "Unique Selection Check",
    "Prior Mapping Check",
    "Evidence Completeness Check",
    "Registry Action",
    "Audit Result",
    "Audit Notes",
)

_CYBER_NAME_TERMS = (
    "cyber",
    "security",
    "infosec",
    "identity",
    "zero trust",
    "threat",
)
_MATURE_SECTOR_TERMS = (
    "banking",
    "insurance",
    "telecom",
    "energy",
    "utilities",
    "semiconductor",
    "automotive",
    "aerospace",
    "defence",
    "financial services",
    "critical infrastructure",
)
_EARLY_CAREER_SECTOR_TERMS = (
    "cyber",
    "technology",
    "software",
    "ict",
    "digital",
    "consult",
)
_ORGANIZATION_NAME_TERMS = (
    "group",
    "bank",
    "insurance",
    "university",
    "telecom",
    "technologies",
    "systems",
)
_LEGAL_NUMBER_PATTERN = re.compile(r"(?:^|\s)\d{5,}(?:\s|$)")


@dataclass(frozen=True)
class Wave6Candidate:
    rank: int
    corporate_cluster_id: str
    representative_employer: str
    priority_score: int
    employer_scale_score: int
    cybersecurity_relevance_score: int
    target_geography_score: int
    early_career_probability_score: int
    cluster_record_score: int
    likely_ats_quality_score: int
    legal_discovery_records: int
    primary_scan_eligible: bool
    sectors: str
    discovery_geographies: str
    organization_types: str
    score_rationale: str


@dataclass(frozen=True)
class Wave6BuildResult:
    selected_clusters: int
    resolved_clusters: int
    deferred_clusters: int
    resolved_records: int
    wave_path: Path
    audit_path: Path
    registry_path: Path


def select_wave6_candidates(
    engine: Engine,
    *,
    limit: int = 100,
    geography_path: Path = PROJECT_ROOT / "config" / "geographies.yaml",
) -> tuple[Wave6Candidate, ...]:
    """Rank unresolved active clusters without making requests or changing the registry."""

    if not 1 <= limit <= 200:
        raise ValueError("Wave 6 selection limit must be between 1 and 200")
    targets, aliases = _load_target_geographies(geography_path)
    with Session(engine) as session:
        resolved = select(ClusterPortalMapping.corporate_cluster_id)
        clusters = session.scalars(
            select(CorporateCluster).where(
                CorporateCluster.active_in_master.is_(True),
                CorporateCluster.corporate_cluster_id.not_in(resolved),
            )
        ).all()

    scored = [_score_cluster(cluster, targets=targets, aliases=aliases) for cluster in clusters]
    ordered = sorted(
        scored,
        key=lambda row: (
            -row["priority_score"],
            -row["cybersecurity_relevance_score"],
            -row["employer_scale_score"],
            -row["likely_ats_quality_score"],
            row["representative_employer"].casefold(),
            row["corporate_cluster_id"],
        ),
    )[:limit]
    return tuple(
        Wave6Candidate(rank=index, **row) for index, row in enumerate(ordered, start=1)
    )


def write_wave6_selection_csv(rows: tuple[Wave6Candidate, ...], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=Wave6Candidate.__dataclass_fields__)
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)


def render_wave6_selection_report(rows: tuple[Wave6Candidate, ...]) -> str:
    lines = [
        "# Wave 6 candidate selection",
        "",
        f"- Selected unresolved clusters: {len(rows)}",
        "- Selection is deterministic and read-only; ranking never creates a portal mapping.",
        "- Score: employer scale (20) + cybersecurity relevance (20) + target geography "
        "(15) + early-career probability (15) + cluster records (15) + likely ATS quality "
        "(15).",
        "- Likely ATS quality is explicitly a review proxy based on employer maturity and name "
        "clarity; it is not evidence that an ATS endpoint exists.",
        "",
        "| Rank | Employer | Score | Scale | Cyber | Geo | Early | Records | ATS proxy |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows[:25]:
        company = row.representative_employer.replace("|", "\\|")
        lines.append(
            f"| {row.rank} | {company} | {row.priority_score} | "
            f"{row.employer_scale_score} | {row.cybersecurity_relevance_score} | "
            f"{row.target_geography_score} | {row.early_career_probability_score} | "
            f"{row.cluster_record_score} | {row.likely_ats_quality_score} |"
        )
    lines.extend(
        [
            "",
            "The complete selection and component scores are available in the companion CSV.",
            "",
        ]
    )
    return "\n".join(lines)


def build_wave6_review_artifacts(
    engine: Engine,
    *,
    selection_path: Path,
    reviewed_path: Path,
    wave_path: Path,
    audit_path: Path,
    registry_path: Path,
) -> Wave6BuildResult:
    """Merge reviewed resolutions with the full selection and validate the registry boundary."""

    selection = _read_selection(selection_path)
    if len(selection) != 100:
        raise ValueError(f"Wave 6 requires exactly 100 selected clusters, got {len(selection)}")
    selected_ids = [row["corporate_cluster_id"] for row in selection]
    if len(set(selected_ids)) != len(selected_ids):
        raise ValueError("Wave 6 selection contains duplicate cluster IDs")
    reviewed = _read_reviewed(reviewed_path)
    unexpected = sorted(set(reviewed) - set(selected_ids))
    if unexpected:
        raise ValueError(f"Reviewed Wave 6 clusters are outside the selection: {unexpected}")

    with Session(engine) as session:
        existing = set(
            session.scalars(
                select(ClusterPortalMapping.corporate_cluster_id).where(
                    ClusterPortalMapping.corporate_cluster_id.in_(selected_ids)
                )
            )
        )
    if existing:
        raise ValueError(f"Wave 6 selection is no longer unresolved: {sorted(existing)}")

    default_deferral = (
        "No unique official careers and job-search endpoint was approved in the bounded "
        "verification tranche; preserve for a later evidence-led review."
    )
    special_deferrals = {
        "CG-D1D9B9355F": (
            "AIR is an ambiguous short name across two source geographies; no parent or "
            "same-name match is forced."
        ),
        "CG-B3DEB52441": (
            "EID is an ambiguous short name across two source geographies; no parent or "
            "same-name match is forced."
        ),
        "CG-B472B60D00": (
            "CyberCX was acquired by Accenture in 2026; defer until its parent "
            "normalization and current recruiting scope are reviewed."
        ),
        "CG-2B5AF07632": (
            "The named Texas Tech institute is an organizational unit rather than a "
            "proven standalone employer portal."
        ),
        "CG-E8223BC889": (
            "Country-specific Orange Cyberdefense identity may share a parent portal; "
            "defer to avoid an unreviewed parent assignment."
        ),
        "CG-90E474B793": (
            "Country-specific Orange Cyberdefense identity may share a parent portal; "
            "defer to avoid an unreviewed parent assignment."
        ),
    }
    wave_rows: list[dict[str, object]] = []
    audit_rows: list[dict[str, str]] = []
    registry_rows: list[dict[str, str]] = []
    resolved_records = 0
    for candidate in selection:
        cluster_id = candidate["corporate_cluster_id"]
        decision = reviewed.get(cluster_id)
        if decision is None:
            wave_rows.append(
                _deferred_wave_row(
                    candidate,
                    special_deferrals.get(cluster_id, default_deferral),
                )
            )
            audit_rows.append(_audit_row(candidate, resolved=False))
            continue
        wave_rows.append(_resolved_wave_row(candidate, decision))
        audit_rows.append(_audit_row(candidate, resolved=True))
        registry_rows.append(_registry_row(decision))
        resolved_records += int(candidate["legal_discovery_records"])

    _write_dict_rows(wave_path, WAVE_HEADERS, wave_rows)
    _write_dict_rows(audit_path, AUDIT_HEADERS, audit_rows)
    from research_agent.company.registry_changes import CHANGE_HEADERS

    _write_dict_rows(registry_path, CHANGE_HEADERS, registry_rows)
    return Wave6BuildResult(
        selected_clusters=len(selection),
        resolved_clusters=len(reviewed),
        deferred_clusters=len(selection) - len(reviewed),
        resolved_records=resolved_records,
        wave_path=wave_path.resolve(),
        audit_path=audit_path.resolve(),
        registry_path=registry_path.resolve(),
    )


def write_wave6_summary(
    *,
    destination: Path,
    build: Wave6BuildResult,
    master_path: Path,
    prior_master_path: Path,
    prior_master_sha256: str,
    import_batch_id: int,
    cumulative_resolved_clusters: int,
    cumulative_resolved_records: int,
    cumulative_unique_jobs_urls: int,
    active_portals: int,
) -> Path:
    summary = {
        "wave": 6,
        "verified_date": "2026-08-31",
        "selection_scoring_version": "wave6-deterministic-v1",
        "selected_clusters": build.selected_clusters,
        "new_resolved_clusters": build.resolved_clusters,
        "deferred_clusters": build.deferred_clusters,
        "new_master_records_covered": build.resolved_records,
        "cumulative_resolved_clusters": cumulative_resolved_clusters,
        "cumulative_resolved_records": cumulative_resolved_records,
        "cumulative_unique_resolved_jobs_urls": cumulative_unique_jobs_urls,
        "active_portals": active_portals,
        "registry_import_batch_id": import_batch_id,
        "prior_synchronized_master": prior_master_path.name,
        "prior_synchronized_master_sha256": prior_master_sha256,
        "prior_master_immutable": _sha256(prior_master_path) == prior_master_sha256,
        "synchronized_master": master_path.name,
        "synchronized_master_sha256": _sha256(master_path),
        "validation": {
            "exact_selection_count": build.selected_clusters == 100,
            "unique_clusters": True,
            "resolved_evidence_complete": True,
            "deferred_without_forced_mapping": True,
            "prior_wave_immutable": _sha256(prior_master_path) == prior_master_sha256,
        },
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination.resolve()


def write_wave6_distribution_zip(destination: Path, files: tuple[Path, ...]) -> Path:
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite Wave 6 distribution: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files, key=lambda item: item.name.casefold()):
            info = zipfile.ZipInfo(path.name, date_time=(2026, 8, 31, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
    return destination.resolve()


def render_wave6_completion_report(
    build: Wave6BuildResult,
    *,
    cumulative_resolved_clusters: int,
    cumulative_resolved_records: int,
    master_path: Path,
    distribution_path: Path,
) -> str:
    return "\n".join(
        [
            "# Portal Resolution Wave 6",
            "",
            f"- Selected clusters: {build.selected_clusters}",
            f"- Newly resolved clusters: {build.resolved_clusters}",
            f"- Deferred without forced mapping: {build.deferred_clusters}",
            f"- Newly covered master records: {build.resolved_records}",
            f"- Cumulative resolved clusters: {cumulative_resolved_clusters}",
            f"- Cumulative resolved records: {cumulative_resolved_records}",
            "- Official-source policy: corporate, careers and job-search endpoints only; "
            "no authenticated scraping or access-control bypass.",
            "- All 100 audit rows pass uniqueness, prior-mapping and evidence/deferral checks.",
            "",
            f"Synchronized master: `{master_path.resolve()}`",
            f"Distribution ZIP: `{distribution_path.resolve()}`",
            "",
        ]
    )


def _score_cluster(
    cluster: CorporateCluster,
    *,
    targets: set[str],
    aliases: dict[str, str],
) -> dict[str, object]:
    name = cluster.representative_canonical_employer.strip()
    name_folded = name.casefold()
    sectors = _json_list(cluster.sectors_json)
    geographies = _json_list(cluster.discovery_geographies_json)
    organization_types = _json_list(cluster.org_types_json)
    sector_text = " | ".join(sectors).casefold()
    org_text = " | ".join(organization_types).casefold()

    if "large-cap" in sector_text:
        scale_score = 20
        scale_reason = "large-cap source stratum"
    elif any(term in org_text for term in ("government", "public", "university")):
        scale_score = 16
        scale_reason = "institutional organization type"
    elif any(term in sector_text for term in _MATURE_SECTOR_TERMS):
        scale_score = 12
        scale_reason = "regulated or mature-employer sector"
    else:
        scale_score = 7
        scale_reason = "company source stratum"

    if any(term in name_folded for term in _CYBER_NAME_TERMS):
        cyber_score = 20
        cyber_reason = "cyber/security employer name"
    elif "cybersecurity vendors" in sector_text:
        cyber_score = 20
        cyber_reason = "cybersecurity-vendor sector"
    elif "cybersecurity" in sector_text:
        cyber_score = 18
        cyber_reason = "explicit cybersecurity sector"
    elif "cyber" in sector_text:
        cyber_score = 15
        cyber_reason = "cyber-adjacent sector"
    elif "security" in sector_text:
        cyber_score = 10
        cyber_reason = "security-adjacent sector"
    elif any(term in sector_text for term in ("technology", "software", "ict", "digital")):
        cyber_score = 8
        cyber_reason = "technology sector"
    else:
        cyber_score = 5
        cyber_reason = "regulated/critical employer baseline"

    normalized_geographies = {aliases.get(value, value) for value in geographies}
    if normalized_geographies & targets:
        geography_score = 15
        geography_reason = "configured target geography"
    elif any("europe" in value.casefold() for value in geographies):
        geography_score = 12
        geography_reason = "included European region"
    else:
        geography_score = 0
        geography_reason = "not a configured target geography"

    early_score = 10 if cluster.has_primary_scan_eligibility else 0
    early_reasons = ["primary scan eligible"] if cluster.has_primary_scan_eligibility else []
    if "company" in org_text:
        early_score += 3
        early_reasons.append("company organization type")
    if any(term in sector_text for term in _EARLY_CAREER_SECTOR_TERMS):
        early_score += 2
        early_reasons.append("technology/cyber hiring sector")
    early_score = min(early_score, 15)

    record_score = min(15, 5 * max(cluster.record_count, 1))

    ats_score = 5
    ats_reasons = ["unverified baseline"]
    if "large-cap" in sector_text:
        ats_score += 6
        ats_reasons.append("large-cap maturity proxy")
    elif any(term in sector_text for term in _MATURE_SECTOR_TERMS):
        ats_score += 4
        ats_reasons.append("mature-sector proxy")
    if any(term in name_folded for term in _ORGANIZATION_NAME_TERMS):
        ats_score += 2
        ats_reasons.append("clear organization name")
    if not _LEGAL_NUMBER_PATTERN.search(name) and len(name) >= 3:
        ats_score += 2
        ats_reasons.append("non-numeric identity")
    ats_score = min(ats_score, 15)

    priority_score = (
        scale_score
        + cyber_score
        + geography_score
        + early_score
        + record_score
        + ats_score
    )
    rationale = "; ".join(
        (
            scale_reason,
            cyber_reason,
            geography_reason,
            ", ".join(early_reasons) or "not primary scan eligible",
            f"{cluster.record_count} source record(s)",
            ", ".join(ats_reasons),
        )
    )
    return {
        "corporate_cluster_id": cluster.corporate_cluster_id,
        "representative_employer": name,
        "priority_score": priority_score,
        "employer_scale_score": scale_score,
        "cybersecurity_relevance_score": cyber_score,
        "target_geography_score": geography_score,
        "early_career_probability_score": early_score,
        "cluster_record_score": record_score,
        "likely_ats_quality_score": ats_score,
        "legal_discovery_records": cluster.record_count,
        "primary_scan_eligible": cluster.has_primary_scan_eligibility,
        "sectors": " | ".join(sectors),
        "discovery_geographies": " | ".join(geographies),
        "organization_types": " | ".join(organization_types),
        "score_rationale": rationale,
    }


def _load_target_geographies(path: Path) -> tuple[set[str], dict[str, str]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    targets = {str(value) for value in data["target_countries"]}
    aliases = {str(key): str(value) for key, value in data.get("aliases", {}).items()}
    return targets, aliases


def _json_list(value: str) -> list[str]:
    parsed = json.loads(value)
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise ValueError("Expected a JSON list of strings in cluster metadata")
    return parsed


def _read_selection(path: Path) -> list[dict[str, object]]:
    expected = tuple(Wave6Candidate.__dataclass_fields__)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != expected:
            raise ValueError("Unexpected Wave 6 selection schema")
        rows: list[dict[str, object]] = []
        for item in reader:
            rows.append(
                {
                    **item,
                    "rank": int(item["rank"]),
                    "priority_score": int(item["priority_score"]),
                    "legal_discovery_records": int(item["legal_discovery_records"]),
                    "primary_scan_eligible": item["primary_scan_eligible"] == "True",
                }
            )
    if [row["rank"] for row in rows] != list(range(1, len(rows) + 1)):
        raise ValueError("Wave 6 selection ranks are not contiguous")
    return rows


def _read_reviewed(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != REVIEW_HEADERS:
            raise ValueError("Unexpected Wave 6 reviewed-resolution schema")
        rows = [{key: (value or "").strip() for key, value in item.items()} for item in reader]
    clusters = [row["Corporate Cluster ID"] for row in rows]
    if len(set(clusters)) != len(clusters):
        raise ValueError("Duplicate reviewed Wave 6 cluster ID")
    for index, row in enumerate(rows, start=2):
        missing = [header for header in REVIEW_HEADERS if not row[header]]
        allowed_blank = {"Resolution Parent Override"}
        missing = [header for header in missing if header not in allowed_blank]
        if missing:
            raise ValueError(f"Reviewed Wave 6 row {index} is missing {missing}")
        if row["Resolution Wave"] != "W6":
            raise ValueError(f"Reviewed Wave 6 row {index} has the wrong wave")
        if not row["Portal Resolution Status"].startswith("VERIFIED"):
            raise ValueError(f"Reviewed Wave 6 row {index} is not verified")
        for field in (
            "Resolved Corporate Website",
            "Resolved Careers Landing URL",
            "Resolved Jobs Search URL",
            "Portal Verification URL",
        ):
            _validate_review_url(row[field], index=index, field=field)
    return {row["Corporate Cluster ID"]: row for row in rows}


def _resolved_wave_row(
    candidate: dict[str, object], decision: dict[str, str]
) -> dict[str, object]:
    return {
        "Corporate Cluster ID": candidate["corporate_cluster_id"],
        "Selection Rank": candidate["rank"],
        "Priority Score": candidate["priority_score"],
        "Representative Employer": candidate["representative_employer"],
        "Legal/Discovery Records Covered": candidate["legal_discovery_records"],
        "Resolution Outcome": "RESOLVED",
        "Corporate Website": decision["Resolved Corporate Website"],
        "Careers Landing URL": decision["Resolved Careers Landing URL"],
        "Jobs Search URL": decision["Resolved Jobs Search URL"],
        "Portal Scope": decision["Portal Scope"],
        "ATS Family": decision["ATS Family"],
        "ATS Confidence": decision["ATS Confidence"],
        "Resolution Status": decision["Portal Resolution Status"],
        "Verification Evidence URL": decision["Portal Verification URL"],
        "Verified Date": decision["Portal Verified Date"],
        "Parent Override": decision["Resolution Parent Override"],
        "Deferral Reason": "",
        "Notes": decision["Reason"],
    }


def _deferred_wave_row(
    candidate: dict[str, object], reason: str
) -> dict[str, object]:
    return {
        "Corporate Cluster ID": candidate["corporate_cluster_id"],
        "Selection Rank": candidate["rank"],
        "Priority Score": candidate["priority_score"],
        "Representative Employer": candidate["representative_employer"],
        "Legal/Discovery Records Covered": candidate["legal_discovery_records"],
        "Resolution Outcome": "DEFERRED",
        "Corporate Website": "",
        "Careers Landing URL": "",
        "Jobs Search URL": "",
        "Portal Scope": "",
        "ATS Family": "",
        "ATS Confidence": "",
        "Resolution Status": "DEFERRED_WAVE6",
        "Verification Evidence URL": "",
        "Verified Date": "",
        "Parent Override": "",
        "Deferral Reason": reason,
        "Notes": "No registry change is emitted for deferred rows.",
    }


def _audit_row(candidate: dict[str, object], *, resolved: bool) -> dict[str, str]:
    return {
        "Corporate Cluster ID": str(candidate["corporate_cluster_id"]),
        "Selection Rank": str(candidate["rank"]),
        "Representative Employer": str(candidate["representative_employer"]),
        "Resolution Outcome": "RESOLVED" if resolved else "DEFERRED",
        "Unique Selection Check": "PASS",
        "Prior Mapping Check": "PASS",
        "Evidence Completeness Check": "PASS",
        "Registry Action": "ADD" if resolved else "NONE",
        "Audit Result": "PASS",
        "Audit Notes": (
            "Complete official endpoint evidence; versioned ADD emitted."
            if resolved
            else "Deferral reason recorded; no endpoint or mapping forced."
        ),
    }


def _registry_row(decision: dict[str, str]) -> dict[str, str]:
    return {
        "Action": "ADD",
        "Corporate Cluster ID": decision["Corporate Cluster ID"],
        "Old Jobs Search URL": "",
        **{
            field: decision[field]
            for field in REVIEW_HEADERS
            if field not in {"Corporate Cluster ID"}
        },
    }


def _write_dict_rows(
    path: Path,
    headers: tuple[str, ...],
    rows: list[dict[str, object]] | list[dict[str, str]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def _validate_review_url(value: str, *, index: int, field: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError(f"Reviewed Wave 6 row {index} has an unsafe {field}: {value}")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"Reviewed Wave 6 row {index} has credentials in {field}")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
