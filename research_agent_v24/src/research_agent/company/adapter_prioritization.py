"""Deterministic ranking of remaining conservative HTML fallback portals."""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import distinct, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_agent.db.models import (
    CanonicalJob,
    ClusterPortalMapping,
    CorporateCluster,
    Portal,
    PortalScanAttempt,
    SourceJob,
)
from research_agent.pipeline.scanner import load_portal_targets
from research_agent.sources.ats.registry import default_adapter_registry


@dataclass(frozen=True)
class AdapterCandidate:
    rank: int
    portal_id: int
    company: str
    jobs_url: str
    host: str
    ats_family: str
    total_score: int
    employer_value_score: int
    likely_yield_score: int
    shared_contract_score: int
    observed_contract_score: int
    cluster_records: int
    observed_jobs: int
    active_review_jobs: int
    same_family_fallbacks: int
    health_state: str
    contract_evidence: str


def rank_fallback_portals(engine: Engine) -> tuple[AdapterCandidate, ...]:
    registry = default_adapter_registry()
    fallback_ids = {
        target.portal_id
        for target in load_portal_targets(engine)
        if (adapter := registry.select(target)) is not None and adapter.name == "official_html"
    }
    if not fallback_ids:
        return ()
    with Session(engine) as session:
        portals = {
            portal.id: portal
            for portal in session.scalars(select(Portal).where(Portal.id.in_(fallback_ids)))
        }
        mapping_rows = session.execute(
            select(ClusterPortalMapping, CorporateCluster)
            .join(
                CorporateCluster,
                CorporateCluster.corporate_cluster_id
                == ClusterPortalMapping.corporate_cluster_id,
            )
            .where(ClusterPortalMapping.portal_id.in_(fallback_ids))
        ).all()
        observed = dict(
            session.execute(
                select(SourceJob.portal_id, func.count(SourceJob.id))
                .where(SourceJob.portal_id.in_(fallback_ids))
                .group_by(SourceJob.portal_id)
            ).all()
        )
        reviews = dict(
            session.execute(
                select(SourceJob.portal_id, func.count(distinct(CanonicalJob.canonical_job_id)))
                .join(
                    CanonicalJob,
                    CanonicalJob.canonical_job_id == SourceJob.canonical_job_id,
                )
                .where(
                    SourceJob.portal_id.in_(fallback_ids),
                    CanonicalJob.active.is_(True),
                    CanonicalJob.filter_status == "REVIEW",
                )
                .group_by(SourceJob.portal_id)
            ).all()
        )
        latest_attempts = _latest_attempts(session, fallback_ids)

    by_portal: dict[int, list[tuple[ClusterPortalMapping, CorporateCluster]]] = {}
    for mapping, cluster in mapping_rows:
        by_portal.setdefault(mapping.portal_id, []).append((mapping, cluster))
    family_by_portal = {
        portal_id: _representative_family(rows) for portal_id, rows in by_portal.items()
    }
    family_counts = Counter(family_by_portal.values())
    unranked: list[dict[str, object]] = []
    for portal_id in fallback_ids:
        portal = portals[portal_id]
        mappings = by_portal.get(portal_id, [])
        clusters = [cluster for _, cluster in mappings]
        family = family_by_portal.get(portal_id, "Unknown")
        records = sum(cluster.record_count for cluster in clusters)
        primary = any(cluster.has_primary_scan_eligibility for cluster in clusters)
        observed_jobs = int(observed.get(portal_id, 0))
        review_jobs = int(reviews.get(portal_id, 0))
        latest = latest_attempts.get(portal_id)
        employer_score = min(records, 20) * 2 + (5 if primary else 0)
        yield_score = min(review_jobs, 10) * 4 + min(observed_jobs, 50) // 5
        leverage_score = min(family_counts[family], 20)
        contract_score = (
            (8 if portal.health_state == "HEALTHY" else 0)
            + (5 if observed_jobs else 0)
            + (3 if latest is not None and latest.status == "SUCCESS" else 0)
        )
        unranked.append(
            {
                "portal_id": portal_id,
                "company": " | ".join(
                    sorted(
                        {cluster.representative_canonical_employer for cluster in clusters},
                        key=str.casefold,
                    )
                ),
                "jobs_url": portal.jobs_search_url,
                "host": portal.host,
                "ats_family": family,
                "total_score": employer_score
                + yield_score
                + leverage_score
                + contract_score,
                "employer_value_score": employer_score,
                "likely_yield_score": yield_score,
                "shared_contract_score": leverage_score,
                "observed_contract_score": contract_score,
                "cluster_records": records,
                "observed_jobs": observed_jobs,
                "active_review_jobs": review_jobs,
                "same_family_fallbacks": family_counts[family],
                "health_state": portal.health_state,
                "contract_evidence": (
                    "successful public response observed"
                    if latest is not None and latest.status == "SUCCESS"
                    else "public contract not yet observed"
                ),
            }
        )
    ordered = sorted(
        unranked,
        key=lambda item: (
            -int(item["total_score"]),
            -int(item["active_review_jobs"]),
            -int(item["observed_jobs"]),
            str(item["company"]).casefold(),
            int(item["portal_id"]),
        ),
    )
    return tuple(
        AdapterCandidate(rank=index, **item)
        for index, item in enumerate(ordered, start=1)
    )


def write_adapter_candidate_csv(rows: tuple[AdapterCandidate, ...], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(AdapterCandidate.__dataclass_fields__)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)


def render_adapter_candidate_report(rows: tuple[AdapterCandidate, ...]) -> str:
    lines = [
        "# Fallback adapter priority",
        "",
        f"- Ranked scannable fallback portals: {len(rows)}",
        "- Scoring: employer value + likely junior/cyber yield + shared-family leverage + "
        "observed public-contract evidence.",
        "- Ranking is a review aid; it never changes routing by itself.",
        "",
        "| Rank | Company | ATS/family evidence | Score | Observed jobs | Review jobs |",
        "|---:|---|---|---:|---:|---:|",
    ]
    for row in rows[:25]:
        company = row.company.replace("|", "\\|")
        family = row.ats_family.replace("|", "\\|")
        lines.append(
            f"| {row.rank} | {company} | {family} | {row.total_score} | "
            f"{row.observed_jobs} | {row.active_review_jobs} |"
        )
    lines.extend(
        [
            "",
            "The complete machine-readable ranking is stored alongside this report as CSV.",
            "",
        ]
    )
    return "\n".join(lines)


def _latest_attempts(
    session: Session,
    portal_ids: set[int | None],
) -> dict[int, PortalScanAttempt]:
    attempts = session.scalars(
        select(PortalScanAttempt)
        .where(PortalScanAttempt.portal_id.in_(portal_ids))
        .order_by(
            PortalScanAttempt.portal_id,
            PortalScanAttempt.scan_run_id.desc(),
            PortalScanAttempt.id.desc(),
        )
    ).all()
    result: dict[int, PortalScanAttempt] = {}
    for attempt in attempts:
        result.setdefault(attempt.portal_id, attempt)
    return result


def _representative_family(
    rows: list[tuple[ClusterPortalMapping, CorporateCluster]],
) -> str:
    families = Counter(mapping.ats_family or "Unknown" for mapping, _ in rows)
    if not families:
        return "Unknown"
    return sorted(families, key=lambda value: (-families[value], value.casefold()))[0]
