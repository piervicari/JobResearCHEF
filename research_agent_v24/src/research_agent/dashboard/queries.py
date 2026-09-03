"""Read-only dashboard queries kept independent from Streamlit rendering."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import distinct, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_agent.db.models import (
    CanonicalJob,
    ClusterPortalMapping,
    CompanyRecord,
    CorporateCluster,
    JobObservation,
    Portal,
    PortalScanAttempt,
    ScanRun,
    SourceJob,
)


@dataclass(frozen=True)
class CoverageSummary:
    master_rows: int
    corporate_clusters: int
    resolved_clusters: int
    unresolved_clusters: int
    unique_portals: int
    scanned_portals: int
    scannable_portals: int
    suspended_portals: int
    healthy_portals: int
    degraded_portals: int
    broken_portals: int
    stale_portals: int
    unknown_portals: int


@dataclass(frozen=True)
class JobSummary:
    total_canonical_jobs: int
    active_jobs: int
    included_active_jobs: int
    review_jobs: int
    closed_jobs: int
    official_only: int
    linkedin_only: int
    found_on_both: int


@dataclass(frozen=True)
class JobActivitySummary:
    latest_run_id: int | None
    new_jobs_latest_run: int
    new_jobs_today: int
    new_jobs_period: int
    period_days: int


def coverage_summary(engine: Engine) -> CoverageSummary:
    with Session(engine) as session:
        master_rows = _count(session, CompanyRecord)
        clusters = _count(session, CorporateCluster)
        resolved = session.scalar(
            select(func.count(distinct(ClusterPortalMapping.corporate_cluster_id)))
        ) or 0
        active_portals = session.scalars(
            select(Portal).where(Portal.active_in_registry.is_(True))
        ).all()
        latest_attempts = _latest_attempt_by_portal(session)
        portal_states = Counter(portal.health_state for portal in active_portals)
        portals = len(active_portals)
        scannable = sum(
            portal.scan_enabled and portal.access_state == "AVAILABLE"
            for portal in active_portals
        )
        scanned = sum(portal.id in latest_attempts for portal in active_portals)
        stale = sum(
            classify_portal_issue(portal, latest_attempts.get(portal.id)) == "STALE_ROUTE"
            for portal in active_portals
        )
    return CoverageSummary(
        master_rows=master_rows,
        corporate_clusters=clusters,
        resolved_clusters=resolved,
        unresolved_clusters=clusters - resolved,
        unique_portals=portals,
        scanned_portals=scanned,
        scannable_portals=scannable,
        suspended_portals=portals - scannable,
        healthy_portals=portal_states.get("HEALTHY", 0),
        degraded_portals=portal_states.get("DEGRADED", 0),
        broken_portals=portal_states.get("BROKEN", 0),
        stale_portals=stale,
        unknown_portals=portal_states.get("UNKNOWN", 0),
    )


def job_summary(engine: Engine) -> JobSummary:
    with Session(engine) as session:
        jobs = session.scalars(select(CanonicalJob)).all()
        source_sets = _source_sets(session)
    official_only = linkedin_only = found_on_both = 0
    for job in jobs:
        sources = source_sets.get(job.canonical_job_id, set())
        has_linkedin = any("linkedin" in source.casefold() for source in sources)
        has_official = any("linkedin" not in source.casefold() for source in sources)
        if has_linkedin and has_official:
            found_on_both += 1
        elif has_linkedin:
            linkedin_only += 1
        elif has_official:
            official_only += 1
    return JobSummary(
        total_canonical_jobs=len(jobs),
        active_jobs=sum(job.active for job in jobs),
        included_active_jobs=sum(
            job.filter_status == "INCLUDE" and job.active for job in jobs
        ),
        review_jobs=sum(job.filter_status == "REVIEW" and job.active for job in jobs),
        closed_jobs=sum(not job.active for job in jobs),
        official_only=official_only,
        linkedin_only=linkedin_only,
        found_on_both=found_on_both,
    )


def job_activity_summary(
    engine: Engine,
    *,
    period_days: int = 7,
    now: datetime | None = None,
) -> JobActivitySummary:
    if period_days < 1:
        raise ValueError("period_days must be at least 1")
    reference = now or datetime.now(UTC)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)
    reference = reference.astimezone(UTC)
    start_of_today = reference.replace(hour=0, minute=0, second=0, microsecond=0)
    period_start = reference - timedelta(days=period_days)
    with Session(engine) as session:
        latest_run = session.scalar(select(ScanRun).order_by(ScanRun.id.desc()).limit(1))
        new_today = session.scalar(
            select(func.count())
            .select_from(CanonicalJob)
            .where(CanonicalJob.first_seen_at >= start_of_today)
        ) or 0
        new_period = session.scalar(
            select(func.count())
            .select_from(CanonicalJob)
            .where(CanonicalJob.first_seen_at >= period_start)
        ) or 0
    return JobActivitySummary(
        latest_run_id=latest_run.id if latest_run is not None else None,
        new_jobs_latest_run=latest_run.new_jobs if latest_run is not None else 0,
        new_jobs_today=new_today,
        new_jobs_period=new_period,
        period_days=period_days,
    )


def job_breakdown_rows(engine: Engine) -> list[dict[str, object]]:
    """Return active canonical-job counts for every required dashboard dimension."""

    with Session(engine) as session:
        jobs = session.execute(
            select(CanonicalJob, CorporateCluster.representative_canonical_employer)
            .outerjoin(
                CorporateCluster,
                CorporateCluster.corporate_cluster_id == CanonicalJob.corporate_cluster_id,
            )
            .where(CanonicalJob.active.is_(True))
        ).all()
        source_sets = _source_sets(session)

    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for job, company in jobs:
        values = {
            "Country": job.country or "Unknown",
            "Company": company or "Unresolved",
            "Cyber category": job.cyber_category or "Review",
            "Seniority": job.seniority or "Review",
            "Workplace": job.workplace_type or "Unknown",
        }
        for dimension, value in values.items():
            counts[dimension][value] += 1
        sources = source_sets.get(job.canonical_job_id, set()) or {"Unknown"}
        for source in sources:
            counts["Source"][source] += 1

    return [
        {"dimension": dimension, "value": value, "active_jobs": count}
        for dimension in (
            "Country",
            "Company",
            "Cyber category",
            "Seniority",
            "Workplace",
            "Source",
        )
        for value, count in sorted(
            counts[dimension].items(), key=lambda item: (-item[1], item[0])
        )
    ]


def job_rows(engine: Engine) -> list[dict[str, object]]:
    with Session(engine) as session:
        rows = session.execute(
            select(CanonicalJob, CorporateCluster.representative_canonical_employer)
            .outerjoin(
                CorporateCluster,
                CorporateCluster.corporate_cluster_id == CanonicalJob.corporate_cluster_id,
            )
            .order_by(CanonicalJob.first_seen_at.desc())
        ).all()
        source_sets = _source_sets(session)
        confidence = _lifecycle_confidence_by_job(session)
    return [
        {
            "canonical_job_id": job.canonical_job_id,
            "title": job.title,
            "company": company or "Unresolved",
            "country": job.country or "Unknown",
            "location": job.location,
            "workplace_type": job.workplace_type or "Unknown",
            "seniority": job.seniority or "Review",
            "cyber_category": job.cyber_category or "Review",
            "filter_status": job.filter_status,
            "active": job.active,
            "lifecycle_confidence": confidence.get(job.canonical_job_id, "incomplete"),
            "posted_at": job.posted_at,
            "first_seen_at": job.first_seen_at,
            "last_seen_at": job.last_seen_at,
            "sources": ", ".join(sorted(source_sets.get(job.canonical_job_id, set()))),
            "apply_url": job.primary_apply_url,
        }
        for job, company in rows
    ]


def review_queue_rows(engine: Engine) -> list[dict[str, object]]:
    with Session(engine) as session:
        rows = session.execute(
            select(CanonicalJob, CorporateCluster.representative_canonical_employer)
            .outerjoin(
                CorporateCluster,
                CorporateCluster.corporate_cluster_id == CanonicalJob.corporate_cluster_id,
            )
            .where(CanonicalJob.active.is_(True), CanonicalJob.filter_status == "REVIEW")
            .order_by(CanonicalJob.first_seen_at.desc())
        ).all()
        latest = _latest_observation_by_job(session)
        source_sets = _source_sets(session)
        confidence = _lifecycle_confidence_by_job(session)
    result: list[dict[str, object]] = []
    for job, company in rows:
        decision, cluster = latest.get(job.canonical_job_id, ({}, {}))
        ambiguity = _ambiguity_signals(decision, cluster)
        result.append(
            {
                "canonical_job_id": job.canonical_job_id,
                "title": job.title,
                "company": company or "Unresolved",
                "location": job.location or "Unknown",
                "seniority": job.seniority or "Unresolved",
                "cyber_category": job.cyber_category or "Unresolved",
                "ambiguity_signals": " | ".join(ambiguity) or "No latest decision evidence",
                "company_resolution": str(cluster.get("method") or "unknown"),
                "lifecycle_confidence": confidence.get(job.canonical_job_id, "incomplete"),
                "sources": ", ".join(
                    sorted(source_sets.get(job.canonical_job_id, set()))
                ),
                "last_seen_at": job.last_seen_at,
                "apply_url": job.primary_apply_url,
            }
        )
    return result


def source_job_rows(engine: Engine, *, active_only: bool = True) -> list[dict[str, object]]:
    with Session(engine) as session:
        statement = select(SourceJob).order_by(SourceJob.last_seen_at.desc())
        if active_only:
            statement = statement.where(SourceJob.is_active.is_(True))
        sources = session.scalars(statement).all()
        latest_attempts = _latest_attempt_by_portal(session)
    rows: list[dict[str, object]] = []
    for source in sources:
        attempt = latest_attempts.get(source.portal_id) if source.portal_id is not None else None
        complete = bool(
            attempt is not None
            and attempt.status == "SUCCESS"
            and attempt.snapshot_complete
        )
        rows.append(
            {
                "source_job_row_id": source.id,
                "canonical_job_id": source.canonical_job_id or "Unresolved",
                "source": source.source,
                "adapter": source.adapter,
                "title": source.raw_title,
                "company": source.raw_company or "Unresolved",
                "location": source.raw_location or "Unknown",
                "active": source.is_active,
                "lifecycle_confidence": "complete" if complete else "incomplete",
                "latest_snapshot_complete": complete,
                "missing_successful_scans": source.missing_successful_scans,
                "last_seen_at": source.last_seen_at,
                "apply_url": source.apply_url,
            }
        )
    return rows


def scan_run_rows(engine: Engine, *, limit: int = 100) -> list[dict[str, object]]:
    with Session(engine) as session:
        runs = session.scalars(select(ScanRun).order_by(ScanRun.id.desc()).limit(limit)).all()
        run_ids = [run.id for run in runs]
        attempts_by_run: dict[int, list[tuple[PortalScanAttempt, str]]] = defaultdict(list)
        if run_ids:
            attempts = session.execute(
                select(PortalScanAttempt, Portal.host)
                .join(Portal, Portal.id == PortalScanAttempt.portal_id)
                .where(PortalScanAttempt.scan_run_id.in_(run_ids))
            ).all()
            for attempt, host in attempts:
                attempts_by_run[attempt.scan_run_id].append((attempt, host))
    return [
        {
            "run_id": run.id,
            "source": run.source,
            "status": run.status,
            "pipeline_status": run.pipeline_status,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "duration_seconds": _duration_seconds(run.started_at, run.finished_at),
            "portals": run.portal_count,
            "successes": run.success_count,
            "failures": run.failure_count,
            "requests": run.request_count,
            "retries": run.retry_count,
            "http_2xx": run.http_2xx_count,
            "http_3xx": run.http_3xx_count,
            "http_4xx": run.http_4xx_count,
            "http_5xx": run.http_5xx_count,
            "http_429": run.http_429_count,
            "failed_domains": len(
                {
                    host
                    for attempt, host in attempts_by_run[run.id]
                    if attempt.status != "SUCCESS"
                }
            ),
            "parser_failures": sum(
                attempt.error_type == "AdapterSchemaError"
                for attempt, _ in attempts_by_run[run.id]
            ),
            "unexpected_empty_complete": sum(
                _is_unexpected_empty_complete(attempt)
                for attempt, _ in attempts_by_run[run.id]
            ),
            "jobs_discovered": run.jobs_discovered,
            "new_jobs": run.new_jobs,
            "updated_jobs": run.updated_jobs,
            "duplicates": run.duplicates,
            "closed_jobs": run.jobs_closed,
        }
        for run in runs
    ]


def portal_rows(engine: Engine) -> list[dict[str, object]]:
    with Session(engine) as session:
        portals = session.scalars(
            select(Portal).where(Portal.active_in_registry.is_(True)).order_by(Portal.host)
        ).all()
        latest_attempts = _latest_attempt_by_portal(session)
    result: list[dict[str, object]] = []
    for portal in portals:
        attempt = latest_attempts.get(portal.id)
        warnings = _json_list(attempt.warnings_json) if attempt is not None else []
        result.append(
            {
            "portal_id": portal.id,
            "host": portal.host,
            "jobs_url": portal.jobs_search_url,
            "clusters": portal.cluster_count,
            "ats_families": portal.ats_families_json,
            "metadata_conflict": portal.metadata_conflict,
            "health": portal.health_state,
            "access_state": portal.access_state,
            "scan_enabled": portal.scan_enabled,
            "cooldown_until": portal.cooldown_until,
            "last_block_reason": portal.last_block_reason,
            "last_http_status": portal.last_http_status,
            "last_successful_scan": portal.last_successful_scan_at,
            "consecutive_failures": portal.consecutive_failures,
            "consecutive_empty_scans": portal.consecutive_empty_scans,
            "latest_attempt_status": attempt.status if attempt is not None else "NEVER_SCANNED",
            "latest_adapter": attempt.adapter if attempt is not None else "Unknown",
            "latest_snapshot_complete": (
                attempt.snapshot_complete if attempt is not None else False
            ),
            "latest_warnings": " | ".join(warnings),
            "latest_error_type": attempt.error_type if attempt is not None else None,
            "latest_error": attempt.error_message if attempt is not None else None,
            "issue_category": classify_portal_issue(portal, attempt),
        }
        )
    return result


def adapter_coverage_rows(engine: Engine) -> list[dict[str, object]]:
    from research_agent.pipeline.scanner import load_portal_targets
    from research_agent.sources.ats.registry import default_adapter_registry

    registry = default_adapter_registry()
    targets = load_portal_targets(engine)
    with Session(engine) as session:
        portal_state = {
            portal.id: portal
            for portal in session.scalars(
                select(Portal).where(Portal.id.in_([t.portal_id for t in targets]))
            )
        }
    grouped: dict[str, dict[str, int]] = {}
    for target in targets:
        adapter = registry.select(target)
        name = adapter.name if adapter is not None else "unsupported"
        state = grouped.setdefault(
            name,
            {"portals": 0, "healthy": 0, "degraded": 0, "unknown": 0},
        )
        state["portals"] += 1
        portal = portal_state.get(target.portal_id)
        if portal is not None:
            key = portal.health_state.casefold()
            if key in state:
                state[key] += 1
    return [
        {
            "adapter": adapter,
            "coverage_type": "incomplete fallback" if adapter == "official_html" else "structured",
            **values,
        }
        for adapter, values in sorted(
            grouped.items(), key=lambda item: (-item[1]["portals"], item[0])
        )
    ]


def high_value_unresolved_rows(engine: Engine, *, limit: int = 100) -> list[dict[str, object]]:
    with Session(engine) as session:
        resolved = select(ClusterPortalMapping.corporate_cluster_id)
        clusters = session.scalars(
            select(CorporateCluster)
            .where(CorporateCluster.corporate_cluster_id.not_in(resolved))
            .order_by(
                CorporateCluster.has_primary_scan_eligibility.desc(),
                CorporateCluster.record_count.desc(),
                CorporateCluster.representative_canonical_employer,
            )
            .limit(limit * 4)
        ).all()
    rows = []
    for cluster in clusters:
        sectors = _json_list(cluster.sectors_json)
        geographies = _json_list(cluster.discovery_geographies_json)
        text = " ".join([cluster.representative_canonical_employer, *sectors]).casefold()
        cyber_signal = any(
            marker in text
            for marker in ("cyber", "security", "technology", "digital", "consult")
        )
        priority_score = (
            min(cluster.record_count, 10) * 2
            + (5 if cluster.has_primary_scan_eligibility else 0)
            + (4 if cyber_signal else 0)
            + (2 if geographies else 0)
        )
        rows.append(
            {
                "corporate_cluster_id": cluster.corporate_cluster_id,
                "company": cluster.representative_canonical_employer,
                "priority_score": priority_score,
                "records": cluster.record_count,
                "primary_scan_eligible": cluster.has_primary_scan_eligibility,
                "sectors": " | ".join(sectors),
                "discovery_geographies": " | ".join(geographies),
            }
        )
    return sorted(
        rows,
        key=lambda row: (-int(row["priority_score"]), -int(row["records"]), str(row["company"])),
    )[:limit]


def discovery_coverage_rows(engine: Engine) -> list[dict[str, object]]:
    return _record_attribute_coverage_rows(
        engine,
        attribute=CompanyRecord.discovery_geography,
        label="discovery_geography",
    )


def sector_coverage_rows(engine: Engine) -> list[dict[str, object]]:
    return _record_attribute_coverage_rows(
        engine,
        attribute=CompanyRecord.sector,
        label="sector",
    )


def _record_attribute_coverage_rows(
    engine: Engine,
    *,
    attribute: Any,
    label: str,
) -> list[dict[str, object]]:
    resolved = (
        select(ClusterPortalMapping.corporate_cluster_id)
        .distinct()
        .subquery("resolved_clusters")
    )
    with Session(engine) as session:
        rows = session.execute(
            select(
                attribute,
                func.count(distinct(CompanyRecord.record_id)),
                func.count(distinct(CompanyRecord.corporate_cluster_id)),
                func.count(distinct(resolved.c.corporate_cluster_id)),
            )
            .outerjoin(
                resolved,
                resolved.c.corporate_cluster_id == CompanyRecord.corporate_cluster_id,
            )
            .group_by(attribute)
            .order_by(func.count(distinct(CompanyRecord.record_id)).desc())
        ).all()
    return [
        {
            label: value,
            "master_rows": master_rows,
            "corporate_clusters": corporate_clusters,
            "resolved_clusters_present": resolved_clusters,
        }
        for value, master_rows, corporate_clusters, resolved_clusters in rows
    ]


def latest_filter_counts(engine: Engine) -> list[dict[str, object]]:
    with Session(engine) as session:
        latest_run_id = session.scalar(select(func.max(JobObservation.scan_run_id)))
        if latest_run_id is None:
            return []
        rows = session.execute(
            select(JobObservation.filter_status, func.count())
            .where(JobObservation.scan_run_id == latest_run_id)
            .group_by(JobObservation.filter_status)
        ).all()
    return [
        {"filter_status": status, "count": count, "scan_run_id": latest_run_id}
        for status, count in rows
    ]


def _source_sets(session: Session) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    rows = session.execute(
        select(SourceJob.canonical_job_id, SourceJob.source).where(
            SourceJob.canonical_job_id.is_not(None)
        )
    ).all()
    for canonical_job_id, source in rows:
        result.setdefault(canonical_job_id, set()).add(source)
    return result


def classify_portal_issue(
    portal: Portal,
    attempt: PortalScanAttempt | None,
) -> str:
    if attempt is None:
        return "NEVER_SCANNED"
    error = attempt.error_type or ""
    message = (attempt.error_message or "").casefold()
    if error == "RobotsDisallowed" or portal.access_state == "ROBOTS_DENIED":
        return "ROBOTS_DENIAL"
    if error in {"AccessChallengeError", "HostCircuitOpenError"} or portal.access_state in {
        "ACCESS_DENIED",
        "CHALLENGE",
    }:
        return "ACCESS_DENIAL"
    if attempt.status == "SUCCESS":
        return "HEALTHY" if not _json_list(attempt.warnings_json) else "WARNING"
    if error == "AdapterSchemaError":
        return "SCHEMA_DRIFT"
    if attempt.http_status == 404 or "not found" in message or "name or service" in message:
        return "STALE_ROUTE"
    return "TRANSIENT_FAILURE"


def _latest_attempt_by_portal(session: Session) -> dict[int, PortalScanAttempt]:
    attempts = session.scalars(
        select(PortalScanAttempt).order_by(
            PortalScanAttempt.portal_id,
            PortalScanAttempt.scan_run_id.desc(),
            PortalScanAttempt.id.desc(),
        )
    ).all()
    result: dict[int, PortalScanAttempt] = {}
    for attempt in attempts:
        result.setdefault(attempt.portal_id, attempt)
    return result


def _lifecycle_confidence_by_job(session: Session) -> dict[str, str]:
    latest_attempts = _latest_attempt_by_portal(session)
    result: dict[str, str] = {}
    sources = session.scalars(
        select(SourceJob).where(SourceJob.canonical_job_id.is_not(None))
    ).all()
    for source in sources:
        current = result.setdefault(source.canonical_job_id or "", "incomplete")
        attempt = latest_attempts.get(source.portal_id) if source.portal_id is not None else None
        if (
            current != "complete"
            and attempt is not None
            and attempt.status == "SUCCESS"
            and attempt.snapshot_complete
        ):
            result[source.canonical_job_id or ""] = "complete"
    return result


def _latest_observation_by_job(
    session: Session,
) -> dict[str, tuple[dict[str, Any], dict[str, Any]]]:
    rows = session.execute(
        select(SourceJob.canonical_job_id, JobObservation)
        .join(JobObservation, JobObservation.source_job_row_id == SourceJob.id)
        .where(SourceJob.canonical_job_id.is_not(None))
        .order_by(JobObservation.id.desc())
    ).all()
    result: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for canonical_job_id, observation in rows:
        if canonical_job_id in result:
            continue
        result[canonical_job_id] = (
            _json_object(observation.filter_decision_json),
            _json_object(observation.cluster_resolution_json),
        )
    return result


def _ambiguity_signals(decision: dict[str, Any], cluster: dict[str, Any]) -> list[str]:
    signals: list[str] = []
    for component in ("cyber", "seniority", "geography"):
        evidence = decision.get(component)
        if isinstance(evidence, dict) and evidence.get("status") == "REVIEW":
            signals.append(f"{component}: {evidence.get('reason', 'review required')}")
    if not cluster.get("corporate_cluster_id"):
        signals.append(f"company: {cluster.get('method', 'unresolved')}")
    return signals


def _json_object(value: str) -> dict[str, Any]:
    try:
        loaded = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _json_list(value: str) -> list[str]:
    try:
        loaded = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(item) for item in loaded] if isinstance(loaded, list) else []


def _duration_seconds(started_at: datetime, finished_at: datetime | None) -> float | None:
    if finished_at is None:
        return None
    return round((finished_at - started_at).total_seconds(), 3)


def _is_unexpected_empty_complete(attempt: PortalScanAttempt) -> bool:
    return (
        attempt.status == "SUCCESS"
        and attempt.snapshot_complete
        and attempt.jobs_observed == 0
        and "upstream reports zero active jobs" not in _json_list(attempt.warnings_json)
    )


def _count(session: Session, model: object) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def summaries_as_dict(engine: Engine) -> dict[str, dict[str, object]]:
    return {
        "coverage": asdict(coverage_summary(engine)),
        "jobs": asdict(job_summary(engine)),
    }


def ai_v2_summary(engine: Engine) -> dict[str, int]:
    """Counts for the AI-first SourceJob product path, independent of legacy CanonicalJob."""

    with Session(engine) as session:
        counts = dict(
            session.execute(
                select(SourceJob.ai_status, func.count(SourceJob.id))
                .where(SourceJob.is_active.is_(True))
                .group_by(SourceJob.ai_status)
            ).all()
        )
    return {
        "pending": int(counts.get("PENDING_AI", 0)),
        "cyber": int(counts.get("CYBER", 0)),
        "non_cyber": int(counts.get("NON_CYBER", 0)),
        "needs_detail": int(counts.get("NEEDS_MORE_DETAIL", 0)),
    }


def ai_cyber_job_rows(engine: Engine) -> list[dict[str, object]]:
    """Latest valid AI analysis for active CYBER SourceJobs."""

    from research_agent.db.models import JobAiAnalysis

    latest_ids = (
        select(
            JobAiAnalysis.source_job_row_id.label("source_job_row_id"),
            func.max(JobAiAnalysis.id).label("latest_id"),
        )
        .where(JobAiAnalysis.valid.is_(True))
        .group_by(JobAiAnalysis.source_job_row_id)
        .subquery()
    )
    with Session(engine) as session:
        rows = session.execute(
            select(SourceJob, JobAiAnalysis)
            .join(
                latest_ids,
                latest_ids.c.source_job_row_id == SourceJob.id,
            )
            .join(JobAiAnalysis, JobAiAnalysis.id == latest_ids.c.latest_id)
            .where(SourceJob.ai_status == "CYBER", SourceJob.is_active.is_(True))
            .order_by(SourceJob.first_seen_at.desc(), SourceJob.id.desc())
        ).all()

    output: list[dict[str, object]] = []
    for job, analysis in rows:
        try:
            payload = json.loads(analysis.analysis_json)
        except (TypeError, json.JSONDecodeError):
            payload = {}
        output.append(
            {
                "company": job.resolved_company_name or job.raw_company or "Unresolved",
                "title": job.detail_title or job.raw_title,
                "role_family": payload.get("role_family"),
                "specializations": ", ".join(payload.get("specializations") or []),
                "seniority": payload.get("seniority"),
                "years_min": payload.get("years_experience_min"),
                "years_max": payload.get("years_experience_max"),
                "location": job.detail_location or job.raw_location,
                "skills_required": ", ".join(payload.get("skills_required") or []),
                "skills_preferred": ", ".join(payload.get("skills_preferred") or []),
                "degree_requirement": payload.get("degree_requirement"),
                "certifications": ", ".join(payload.get("certifications") or []),
                "first_seen_at": job.first_seen_at,
                "last_seen_at": job.last_seen_at,
                "posted_at": job.posted_at,
                "apply_url": job.apply_url,
                "source_url": job.detail_url or job.source_url,
                "description_chars": len(job.detail_description or job.raw_description or ""),
                "detail_enriched": bool(job.detail_description),
                "adapter": job.adapter,
                "model": analysis.model,
            }
        )
    return output
