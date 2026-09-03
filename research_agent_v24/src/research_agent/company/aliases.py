"""Versioned company aliases and read-only fuzzy candidate generation."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_agent.company.importer import file_sha256
from research_agent.db.migrations import create_schema
from research_agent.db.models import CompanyAlias, CorporateCluster, ImportBatch, utc_now
from research_agent.filters.common import normalize_text

ALIAS_HEADERS = (
    "Alias",
    "Corporate Cluster ID",
    "Status",
    "Provenance",
    "Evidence Reference",
    "Reason",
)
VALID_ALIAS_STATUSES = {"PROPOSED", "VERIFIED"}


class CompanyAliasError(ValueError):
    pass


@dataclass(frozen=True)
class CompanyAliasImportResult:
    import_batch_id: int
    source_sha256: str
    rows: int
    created: int
    promoted: int
    already_imported: bool


@dataclass(frozen=True)
class CompanyAliasProposal:
    corporate_cluster_id: str
    representative_company: str
    matched_name: str
    matched_name_source: str
    score: float


def read_company_aliases(path: Path) -> list[dict[str, str]]:
    with path.expanduser().resolve().open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != ALIAS_HEADERS:
            raise CompanyAliasError(
                f"Expected alias headers {list(ALIAS_HEADERS)}, got {list(reader.fieldnames or ())}"
            )
        rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
    seen: set[tuple[str, str]] = set()
    for row_number, row in enumerate(rows, start=2):
        normalized = normalize_text(row["Alias"])
        status = row["Status"].upper()
        key = (normalized, row["Corporate Cluster ID"])
        if not normalized or not row["Corporate Cluster ID"]:
            raise CompanyAliasError(f"Alias and cluster are required at row {row_number}")
        if key in seen:
            raise CompanyAliasError(f"Duplicate alias/cluster at row {row_number}: {key}")
        seen.add(key)
        if status not in VALID_ALIAS_STATUSES:
            raise CompanyAliasError(f"Invalid alias status at row {row_number}: {status!r}")
        if not row["Provenance"] or not row["Reason"]:
            raise CompanyAliasError(f"Provenance and reason are required at row {row_number}")
        if status == "VERIFIED" and not row["Evidence Reference"]:
            raise CompanyAliasError(
                f"VERIFIED alias requires an evidence reference at row {row_number}"
            )
        row["Status"] = status
    return rows


def import_company_aliases(
    engine: Engine,
    path: Path,
    *,
    source_version: str,
) -> CompanyAliasImportResult:
    create_schema(engine)
    resolved = path.expanduser().resolve()
    rows = read_company_aliases(resolved)
    source_sha = file_sha256(resolved)
    with Session(engine) as session, session.begin():
        existing_batch = session.scalar(
            select(ImportBatch).where(ImportBatch.source_sha256 == source_sha)
        )
        if existing_batch is not None:
            if (
                existing_batch.source_kind != "company_aliases"
                or existing_batch.status != "COMPLETED"
            ):
                raise CompanyAliasError(
                    f"Checksum belongs to incompatible import batch {existing_batch.id}"
                )
            evidence = json.loads(existing_batch.validation_json or "{}")
            return CompanyAliasImportResult(
                import_batch_id=existing_batch.id,
                source_sha256=source_sha,
                rows=int(existing_batch.row_count or 0),
                created=int(evidence.get("created", 0)),
                promoted=int(evidence.get("promoted", 0)),
                already_imported=True,
            )

        clusters = {
            cluster_id
            for (cluster_id,) in session.execute(select(CorporateCluster.corporate_cluster_id))
        }
        missing = sorted({row["Corporate Cluster ID"] for row in rows} - clusters)
        if missing:
            raise CompanyAliasError(f"Unknown corporate clusters: {missing}")

        batch = ImportBatch(
            source_kind="company_aliases",
            source_filename=resolved.name,
            source_path=str(resolved),
            source_sha256=source_sha,
            source_version=source_version,
            status="RUNNING",
        )
        session.add(batch)
        session.flush()
        created = promoted = 0
        for row in rows:
            normalized = normalize_text(row["Alias"])
            cluster_id = row["Corporate Cluster ID"]
            if row["Status"] == "VERIFIED":
                conflicting = session.scalar(
                    select(CompanyAlias).where(
                        CompanyAlias.normalized_alias == normalized,
                        CompanyAlias.status == "VERIFIED",
                        CompanyAlias.corporate_cluster_id != cluster_id,
                    )
                )
                if conflicting is not None:
                    raise CompanyAliasError(
                        f"VERIFIED alias {row['Alias']!r} conflicts with cluster "
                        f"{conflicting.corporate_cluster_id}"
                    )
            alias = session.scalar(
                select(CompanyAlias).where(
                    CompanyAlias.normalized_alias == normalized,
                    CompanyAlias.corporate_cluster_id == cluster_id,
                )
            )
            if alias is None:
                alias = CompanyAlias(
                    alias=row["Alias"],
                    normalized_alias=normalized,
                    corporate_cluster_id=cluster_id,
                    status=row["Status"],
                    provenance=row["Provenance"],
                    evidence_reference=row["Evidence Reference"],
                    reason=row["Reason"],
                    import_batch_id=batch.id,
                )
                session.add(alias)
                created += 1
                continue
            if alias.status == "VERIFIED" and row["Status"] == "PROPOSED":
                raise CompanyAliasError(f"Refusing to demote VERIFIED alias {alias.alias!r}")
            if alias.status == "PROPOSED" and row["Status"] == "VERIFIED":
                promoted += 1
            alias.alias = row["Alias"]
            alias.status = row["Status"]
            alias.provenance = row["Provenance"]
            alias.evidence_reference = row["Evidence Reference"]
            alias.reason = row["Reason"]
            alias.import_batch_id = batch.id
            alias.updated_at = utc_now()

        batch.status = "COMPLETED"
        batch.finished_at = utc_now()
        batch.row_count = len(rows)
        batch.validation_json = json.dumps(
            {"created": created, "promoted": promoted},
            sort_keys=True,
            separators=(",", ":"),
        )
        return CompanyAliasImportResult(
            import_batch_id=batch.id,
            source_sha256=source_sha,
            rows=len(rows),
            created=created,
            promoted=promoted,
            already_imported=False,
        )


def propose_company_aliases(
    engine: Engine,
    raw_company: str,
    *,
    threshold: float = 0.72,
    limit: int = 5,
) -> tuple[CompanyAliasProposal, ...]:
    """Return candidates without writing aliases or cluster assignments."""

    if not 0 <= threshold <= 1:
        raise ValueError("threshold must be between 0 and 1")
    if limit < 1:
        raise ValueError("limit must be positive")
    query = normalize_text(raw_company)
    if not query:
        return ()
    create_schema(engine)
    with Session(engine) as session:
        clusters = session.scalars(select(CorporateCluster)).all()
        verified_aliases = session.scalars(
            select(CompanyAlias).where(CompanyAlias.status == "VERIFIED")
        ).all()
    names_by_cluster: dict[str, list[tuple[str, str]]] = defaultdict(list)
    representatives: dict[str, str] = {}
    for cluster in clusters:
        representatives[cluster.corporate_cluster_id] = cluster.representative_canonical_employer
        names = {
            cluster.representative_canonical_employer,
            *json.loads(cluster.canonical_employers_json),
            *json.loads(cluster.parent_groups_json),
        }
        names_by_cluster[cluster.corporate_cluster_id].extend(
            (name, "master") for name in names if normalize_text(name)
        )
    for alias in verified_aliases:
        names_by_cluster[alias.corporate_cluster_id].append((alias.alias, "verified_alias"))

    proposals: list[CompanyAliasProposal] = []
    for cluster_id, names in names_by_cluster.items():
        scored = [
            (SequenceMatcher(None, query, normalize_text(name)).ratio(), name, source)
            for name, source in names
        ]
        score, matched_name, source = max(scored, key=lambda item: item[0])
        if score >= threshold:
            proposals.append(
                CompanyAliasProposal(
                    corporate_cluster_id=cluster_id,
                    representative_company=representatives[cluster_id],
                    matched_name=matched_name,
                    matched_name_source=source,
                    score=score,
                )
            )
    return tuple(
        sorted(
            proposals,
            key=lambda item: (-item.score, item.representative_company.casefold()),
        )[:limit]
    )
