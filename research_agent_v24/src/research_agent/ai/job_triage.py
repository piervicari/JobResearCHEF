"""High-recall, low-output LLM triage for large job catalogs.

This stage reduces LLM *call count* for free-provider operation. It is deliberately
semantic (LLM-based), not a keyword filter. Only jobs that are clearly non-cyber are
removed from the full-analysis queue; cyber/ambiguous jobs remain PENDING_AI.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_agent.ai.llm_router import RoutedStructuredLlmClient
from research_agent.config import LlmSettings
from research_agent.db.migrations import create_schema
from research_agent.db.models import JobAiAnalysis, SourceJob


class JobTriageDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: int
    candidate_cyber: bool
    short_reason: str | None = None


class JobTriageBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    jobs: list[JobTriageDecision] = Field(default_factory=list)


@dataclass(frozen=True)
class TriageInput:
    job_id: int
    company: str
    title: str
    location: str
    metadata: str
    description_snippet: str
    input_sha256: str


@dataclass(frozen=True)
class TriageSummary:
    selected_jobs: int
    batches_attempted: int
    batches_succeeded: int
    api_failures: int
    obvious_non_cyber: int
    candidates_for_full_analysis: int
    still_pending_jobs: int


class RoutedJobTriageAnalyzer:
    """Small-output, high-recall triage using the existing routed LLM client."""

    SYSTEM_PROMPT = """You perform HIGH-RECALL triage for a cybersecurity job database.

For every supplied job, decide only whether it must continue to the expensive full
cybersecurity analysis stage.

candidate_cyber=true when the role is cybersecurity OR plausibly/ambiguously related to
cybersecurity. Be conservative about false negatives: security engineering, AppSec,
product/cloud security, IAM, GRC/technology risk/security compliance, privacy engineering,
SOC/IR/detection, threat intelligence, vulnerability research/management, offensive
security, security architecture, OT/ICS, cryptography and AI security must continue.
If the supplied evidence is insufficient or ambiguous, candidate_cyber MUST be true.

candidate_cyber=false ONLY when the posting is clearly a non-cyber role. This explicitly
includes payment/merchant fraud operations, AML, KYC/KYB, financial crime, credit risk,
generic enterprise or operational risk, generic regulatory/legal compliance, physical
security, generic trust & safety, generic audit/privacy, sales, marketing, HR, generic
product/design, and generic software/AI/cloud engineering when the actual responsibilities
are not information/cyber security. Security GRC and information-security controls remain
candidates; AML compliance and generic enterprise risk do not. Fraud-related engineering
continues only when the core work is technical security/cyber attack detection, not ordinary
merchant/payment fraud operations. The fact that an employer sells security products does
not make every role cyber.

Return exactly one compact result for every supplied job_id, no extra job IDs. Keep
short_reason brief. Do not extract skills, seniority, degrees or certifications here."""

    def __init__(
        self,
        settings: LlmSettings,
        *,
        route_name: str = "job_light_classification",
        event_callback: Callable[[dict], None] | None = None,
    ) -> None:
        self.settings = settings
        self.route_name = route_name
        self.prompt_version = settings.triage_prompt_version
        self.schema_version = settings.triage_schema_version
        self.router = RoutedStructuredLlmClient(settings, event_callback=event_callback)
        self.last_model = f"routed:{route_name}"
        self.last_repaired_by: str | None = None

    def route_description(self) -> list[dict]:
        return self.router.route_description(self.route_name)

    def analyze_batch(self, jobs: list[TriageInput]) -> list[JobTriageDecision]:
        if not jobs:
            return []
        request_jobs = [
            {
                "job_id": item.job_id,
                "company": item.company,
                "title": item.title,
                "location": item.location,
                "metadata": item.metadata,
                "description_snippet": item.description_snippet,
            }
            for item in jobs
        ]
        schema = JobTriageBatch.model_json_schema()
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {"jobs": request_jobs}, ensure_ascii=False, separators=(",", ":")
                ),
            },
        ]

        expected = [item.job_id for item in jobs]

        def validate(candidate: dict) -> dict:
            try:
                parsed = JobTriageBatch.model_validate(candidate)
            except ValidationError as exc:
                raise ValueError(f"Triage output failed schema validation: {exc}") from exc
            actual = [item.job_id for item in parsed.jobs]
            if len(actual) != len(set(actual)):
                raise ValueError("Triage output contains duplicate job IDs")
            if set(actual) != set(expected):
                missing = sorted(set(expected) - set(actual))
                extra = sorted(set(actual) - set(expected))
                raise ValueError(f"Triage job ID mismatch: missing={missing} extra={extra}")
            return parsed.model_dump(mode="json")

        result = self.router.chat_json(
            route_name=self.route_name,
            messages=messages,
            schema_name="cyber_job_triage_batch",
            schema=schema,
            validator=validate,
        )
        self.last_model = f"{result.provider}/{result.model}"
        self.last_repaired_by = result.repaired_by
        return JobTriageBatch.model_validate(result.data).jobs


def preview_pending_triage(
    engine: Engine, *, limit: int, portal_ids: set[int] | None = None
) -> list[TriageInput]:
    create_schema(engine)
    with Session(engine) as session:
        statement = (
            select(SourceJob)
            .where(SourceJob.ai_status == "PENDING_AI", SourceJob.is_active.is_(True))
            .order_by(SourceJob.id)
        )
        if portal_ids is not None:
            statement = statement.where(SourceJob.portal_id.in_(portal_ids))
        rows = session.scalars(statement.limit(limit)).all()
        return [_triage_input(row) for row in rows]


def triage_pending_jobs(
    engine: Engine,
    analyzer: RoutedJobTriageAnalyzer,
    *,
    limit: int,
    batch_size: int,
    progress_callback: Callable[[dict], None] | None = None,
    portal_ids: set[int] | None = None,
) -> TriageSummary:
    if limit < 1 or batch_size < 1:
        raise ValueError("limit and batch_size must be >= 1")
    inputs = preview_pending_triage(engine, limit=limit, portal_ids=portal_ids)
    attempted = succeeded = failures = obvious_non_cyber = candidates = 0

    for offset in range(0, len(inputs), batch_size):
        batch = inputs[offset : offset + batch_size]
        attempted += 1
        if progress_callback:
            progress_callback(
                {
                    "event": "batch_start",
                    "batch_index": attempted,
                    "batch_count": (len(inputs) + batch_size - 1) // batch_size,
                    "jobs": len(batch),
                    "job_ids": [item.job_id for item in batch],
                }
            )
        try:
            decisions = analyzer.analyze_batch(batch)
        except Exception as exc:
            failures += 1
            if progress_callback:
                progress_callback(
                    {
                        "event": "batch_failed",
                        "batch_index": attempted,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
            # High-recall failure behavior: leave all jobs PENDING_AI. No job is lost.
            continue

        decision_by_id = {item.job_id: item for item in decisions}
        input_by_id = {item.job_id: item for item in batch}
        model = analyzer.last_model
        repaired_by = analyzer.last_repaired_by
        analysis_model = model if not repaired_by else f"{model} [json_repair={repaired_by}]"
        now = datetime.now(UTC)

        with Session(engine) as session, session.begin():
            rows = {
                row.id: row
                for row in session.scalars(
                    select(SourceJob).where(SourceJob.id.in_(list(decision_by_id)))
                ).all()
            }
            for job_id, decision in decision_by_id.items():
                source = rows[job_id]
                triage_input = input_by_id[job_id]
                # Persist a compact audit record using the existing versioned analysis table.
                analysis_payload = {
                    "job_id": job_id,
                    "is_cybersecurity": None if decision.candidate_cyber else False,
                    "needs_more_detail": bool(decision.candidate_cyber),
                    "role_family": None,
                    "specializations": [],
                    "seniority": None,
                    "years_experience_min": None,
                    "years_experience_max": None,
                    "skills_required": [],
                    "skills_preferred": [],
                    "degree_requirement": None,
                    "certifications": [],
                    "short_reason": decision.short_reason,
                    "triage_candidate_cyber": decision.candidate_cyber,
                }
                encoded = json.dumps(
                    analysis_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                existing = session.scalar(
                    select(JobAiAnalysis).where(
                        JobAiAnalysis.source_job_row_id == source.id,
                        JobAiAnalysis.model == f"triage:{analysis_model}",
                        JobAiAnalysis.prompt_version == analyzer.prompt_version,
                        JobAiAnalysis.schema_version == analyzer.schema_version,
                        JobAiAnalysis.input_payload_sha256 == triage_input.input_sha256,
                    )
                )
                if existing is None:
                    session.add(
                        JobAiAnalysis(
                            source_job_row_id=source.id,
                            analyzed_at=now,
                            model=f"triage:{analysis_model}",
                            prompt_version=analyzer.prompt_version,
                            schema_version=analyzer.schema_version,
                            input_payload_sha256=triage_input.input_sha256,
                            is_cybersecurity=(None if decision.candidate_cyber else False),
                            needs_more_detail=bool(decision.candidate_cyber),
                            valid=True,
                            analysis_json=encoded,
                            error=None,
                        )
                    )
                else:
                    existing.analyzed_at = now
                    existing.analysis_json = encoded
                    existing.error = None
                    existing.valid = True
                source.ai_attempts += 1
                source.ai_last_error = None
                source.ai_last_analyzed_at = now
                if decision.candidate_cyber:
                    # Remains queued for the full JobAnalyzer.
                    source.ai_status = "PENDING_AI"
                    candidates += 1
                else:
                    source.ai_status = "NON_CYBER"
                    obvious_non_cyber += 1
        succeeded += 1
        if progress_callback:
            progress_callback(
                {
                    "event": "batch_success",
                    "batch_index": attempted,
                    "model": model,
                    "jobs": len(decisions),
                }
            )

    with Session(engine) as session:
        pending_statement = select(SourceJob.id).where(
            SourceJob.ai_status == "PENDING_AI", SourceJob.is_active.is_(True)
        )
        if portal_ids is not None:
            pending_statement = pending_statement.where(SourceJob.portal_id.in_(portal_ids))
        pending = len(session.scalars(pending_statement).all())
    return TriageSummary(
        selected_jobs=len(inputs),
        batches_attempted=attempted,
        batches_succeeded=succeeded,
        api_failures=failures,
        obvious_non_cyber=obvious_non_cyber,
        candidates_for_full_analysis=candidates,
        still_pending_jobs=pending,
    )


def _triage_input(row: SourceJob) -> TriageInput:
    description = row.detail_description or row.raw_description or ""
    company = row.resolved_company_name or row.raw_company or ""
    title = row.detail_title or row.raw_title
    location = row.detail_location or row.raw_location or ""
    metadata = _compact_source_metadata(row.raw_payload_json)
    snippet = description[:1600]
    payload = {
        "job_id": row.id,
        "company": company,
        "title": title,
        "location": location,
        "metadata": metadata,
        "description_snippet": snippet,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return TriageInput(
        job_id=row.id,
        company=company,
        title=title,
        location=location,
        metadata=metadata,
        description_snippet=snippet,
        input_sha256=hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
    )


def _compact_source_metadata(raw_payload_json: str) -> str:
    try:
        payload = json.loads(raw_payload_json or "{}")
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, dict):
        return ""
    # Greenhouse/Ashby/Lever commonly expose these fields. Keep this mechanical:
    # semantic interpretation belongs to the LLM.
    pieces: list[str] = []
    for key in ("departments", "department", "offices", "team", "employmentType", "workplaceType"):
        value = payload.get(key)
        if value in (None, "", [], {}):
            continue
        if isinstance(value, list):
            names = []
            for item in value[:10]:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("title")
                    if name:
                        names.append(str(name))
                elif item:
                    names.append(str(item))
            rendered = ", ".join(names)
        elif isinstance(value, dict):
            rendered = str(value.get("name") or value.get("title") or "")
        else:
            rendered = str(value)
        if rendered:
            pieces.append(f"{key}={rendered}")
    return "; ".join(pieces)
