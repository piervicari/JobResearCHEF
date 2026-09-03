"""Offline preparation of legacy SourceJob rows for the V2 AI-first pipeline."""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_agent.company.clustering import PortalClusterResolver
from research_agent.db.migrations import create_schema
from research_agent.db.models import SourceJob
from research_agent.pipeline.payload import serialize_observation_payload
from research_agent.sources.base import RawJob


@dataclass(frozen=True)
class V2PreparationSummary:
    inspected: int
    company_identity_backfilled: int
    native_source_id_backfilled: int
    payloads_converted: int
    unresolved_exact_cluster: int
    requeued_for_ai: int


def prepare_legacy_source_jobs_for_v2(engine: Engine, *, dry_run: bool = False) -> V2PreparationSummary:
    """Convert current SourceJob state without making any network or LLM requests."""

    create_schema(engine)
    with Session(engine) as session:
        resolver = PortalClusterResolver(session)
        rows = session.scalars(select(SourceJob).order_by(SourceJob.id)).all()

        company_backfilled = 0
        native_backfilled = 0
        payloads_converted = 0
        unresolved = 0
        requeued = 0

        for source in rows:
            native_id = source.native_source_job_id or source.source_job_id
            if not source.native_source_job_id:
                native_backfilled += 1

            cluster_id = source.resolved_corporate_cluster_id or ""
            company_name = source.resolved_company_name or ""
            if not cluster_id or not company_name:
                resolution = (
                    resolver.resolve(portal_id=source.portal_id, raw_company=source.raw_company)
                    if source.portal_id is not None
                    else resolver.resolve_company(source.raw_company)
                )
                if resolution.corporate_cluster_id is not None:
                    cluster_id = resolution.corporate_cluster_id
                    company_backfilled += 1
                else:
                    unresolved += 1
                company_name = resolver.display_company_name(
                    portal_id=source.portal_id,
                    raw_company=source.raw_company,
                    resolution=resolution,
                )

            raw_job = RawJob(
                source=source.source,
                source_job_id=native_id,
                source_url=source.source_url,
                apply_url=source.apply_url,
                title=source.raw_title,
                company=source.raw_company,
                location=source.raw_location,
                country=source.raw_country or None,
                city=source.raw_city or None,
                description=source.raw_description,
                posted_at=source.posted_at,
                employment_type=source.raw_employment_type or None,
                workplace_type=source.raw_workplace_type or None,
                ats_job_id=source.ats_job_id,
                requisition_id=source.requisition_id,
                raw_payload=_extract_native_payload(source.raw_payload_json),
            )
            payload_json, payload_sha = serialize_observation_payload(
                raw_job,
                company_id=cluster_id or None,
                company_name=company_name,
                adapter=source.adapter,
            )
            changed = source.payload_sha256 != payload_sha or not _is_v2_envelope(
                source.raw_payload_json
            )
            if changed:
                payloads_converted += 1
                if source.ai_status != "PENDING_AI":
                    requeued += 1

            if dry_run:
                continue
            source.native_source_job_id = native_id
            source.resolved_corporate_cluster_id = cluster_id
            source.resolved_company_name = company_name
            source.payload_sha256 = payload_sha
            source.raw_payload_json = payload_json
            if changed:
                source.ai_status = "PENDING_AI"
                source.ai_last_error = None

        if not dry_run:
            session.commit()

    return V2PreparationSummary(
        inspected=len(rows),
        company_identity_backfilled=company_backfilled,
        native_source_id_backfilled=native_backfilled,
        payloads_converted=payloads_converted,
        unresolved_exact_cluster=unresolved,
        requeued_for_ai=requeued,
    )


def _extract_native_payload(value: str | None) -> dict[str, object] | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    native = parsed.get("source_native_payload") if "canonical" in parsed else parsed
    return native if isinstance(native, dict) else None


def _is_v2_envelope(value: str | None) -> bool:
    if not value:
        return False
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return False
    return isinstance(parsed, dict) and isinstance(parsed.get("canonical"), dict)
