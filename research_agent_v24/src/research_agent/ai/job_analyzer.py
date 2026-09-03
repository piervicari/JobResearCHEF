"""Batch JobAnalyzer with a small OpenAI-compatible HTTP client.

The network scan and LLM are intentionally decoupled. This module only reads local
SourceJob rows that are already PENDING_AI and writes versioned analysis records.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Callable, Protocol

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_agent.ai.llm_router import RoutedStructuredLlmClient
from research_agent.ai.schema import JobAnalysis, JobAnalysisBatch
from research_agent.config import LlmSettings
from research_agent.db.migrations import create_schema
from research_agent.db.models import JobAiAnalysis, SourceJob


SUBSTANTIVE_DESCRIPTION_CHARS = 1000


@dataclass(frozen=True)
class AnalysisInput:
    job_id: int
    company: str
    title: str
    location: str
    country: str
    city: str
    employment_type: str
    workplace_type: str
    description: str
    source_url: str
    payload_sha256: str


@dataclass(frozen=True)
class AnalyzePendingSummary:
    selected_jobs: int
    batches_attempted: int
    batches_succeeded: int
    api_failures: int
    analyzed_jobs: int
    cyber_jobs: int
    non_cyber_jobs: int
    needs_more_detail_jobs: int
    still_pending_jobs: int


@dataclass(frozen=True)
class SemanticCleanupCandidate:
    job_id: int
    company: str
    title: str
    description_chars: int
    current_status: str


@dataclass(frozen=True)
class SemanticCleanupSummary:
    selected_jobs: int
    requeued_jobs: int


class BatchAnalyzer(Protocol):
    model: str
    prompt_version: str
    schema_version: str

    def analyze_batch(self, jobs: list[AnalysisInput]) -> list[JobAnalysis]: ...


class RoutedJobAnalyzer:
    """Structured batch analyzer using task-specific quality/fallback routing."""

    SYSTEM_PROMPT = """You classify job postings for a cybersecurity career research database.

Cybersecurity means information/cyber security work: include security engineering,
application/product/cloud/infrastructure security, SOC/detection/incident response/DFIR,
threat intelligence/research, vulnerability management, IAM/PAM/authentication/authorization,
security GRC, information-security risk, IT/security controls, privacy engineering when
materially technical/security-related, OT/ICS security, security architecture, offensive
security, cryptography, and AI/ML security.

Keep the dataset semantically narrow. Payment or merchant fraud operations, AML, KYC/KYB,
financial crime, credit risk, generic enterprise/operational risk, generic regulatory or
legal compliance, physical security, generic trust & safety, generic audit/privacy, generic
IT, and generic software/AI/cloud engineering are NON_CYBER unless the posting itself shows
that the core responsibilities are genuinely information/cyber security. A role can be
interesting to a security candidate without being a cybersecurity job.

Boundary examples: Security GRC -> CYBER; Enterprise Risk Management -> NON_CYBER.
Information Security Compliance -> CYBER; AML Compliance -> NON_CYBER. Security engineering
for cyber attack/fraud detection -> CYBER; merchant/payment fraud operations -> NON_CYBER.

All seniorities are valid. Never reject a job because it is senior/staff/principal/manager.
Extract only evidence supported by the posting. Prefer null/empty lists over guessing.
Use NEEDS_MORE_DETAIL only when the supplied evidence is genuinely insufficient to
classify the role. If a substantive job description is supplied, make a supported binary
decision: CYBER or NON_CYBER. In particular, if the description shows that security is
only incidental/nice-to-have and the core work is cloud, software, AI, sales, HR, etc.,
classify NON_CYBER rather than NEEDS_MORE_DETAIL.

Return exactly one result for every supplied job_id and no additional job IDs."""

    def __init__(
        self,
        settings: LlmSettings,
        *,
        route_name: str = "job_analysis",
        event_callback: Callable[[dict], None] | None = None,
    ) -> None:
        self.settings = settings
        self.route_name = route_name
        self.prompt_version = settings.prompt_version
        self.schema_version = settings.schema_version
        self.router = RoutedStructuredLlmClient(settings, event_callback=event_callback)
        self.model = f"routed:{route_name}"
        self.last_model = self.model
        self.last_provider = "router"
        self.last_repaired_by: str | None = None

    def route_description(self) -> list[dict]:
        return self.router.route_description(self.route_name)

    def analyze_batch(self, jobs: list[AnalysisInput]) -> list[JobAnalysis]:
        if not jobs:
            return []
        request_jobs = [
            {
                "job_id": job.job_id,
                "company": job.company,
                "title": job.title,
                "location": job.location,
                "country": job.country,
                "city": job.city,
                "employment_type": job.employment_type,
                "workplace_type": job.workplace_type,
                "source_url": job.source_url,
                "description": _bounded_description(
                    job.description, self.settings.max_description_chars
                ),
            }
            for job in jobs
        ]
        schema = JobAnalysisBatch.model_json_schema()
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {"jobs": request_jobs}, ensure_ascii=False, separators=(",", ":")
                ),
            },
        ]

        def validate(candidate: dict) -> dict:
            try:
                parsed = JobAnalysisBatch.model_validate(candidate)
            except ValidationError as exc:
                raise ValueError(f"LLM output failed schema validation: {exc}") from exc
            _validate_batch_ids(jobs, parsed.jobs)
            _validate_semantic_completeness(jobs, parsed.jobs)
            return parsed.model_dump(mode="json")

        result = self.router.chat_json(
            route_name=self.route_name,
            messages=messages,
            schema_name="cyber_job_analysis_batch",
            schema=schema,
            validator=validate,
        )
        self.last_provider = result.provider
        self.last_model = f"{result.provider}/{result.model}"
        self.last_repaired_by = result.repaired_by
        parsed = JobAnalysisBatch.model_validate(result.data)
        return parsed.jobs


# Backward-compatible import name for external code; the implementation is now routed.
OpenAICompatibleJobAnalyzer = RoutedJobAnalyzer


def analyze_pending_jobs(
    engine: Engine,
    analyzer: BatchAnalyzer,
    *,
    limit: int,
    batch_size: int,
    progress_callback: Callable[[dict], None] | None = None,
    portal_ids: set[int] | None = None,
) -> AnalyzePendingSummary:
    """Analyze a bounded local queue; one failed batch never deletes/re-fetches jobs."""

    if limit < 1:
        raise ValueError("limit must be >= 1")
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
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
        inputs = [_analysis_input(row) for row in rows]

    batches_attempted = 0
    batches_succeeded = 0
    failures = 0
    analyzed = 0
    cyber = 0
    non_cyber = 0
    needs_detail = 0

    for offset in range(0, len(inputs), batch_size):
        batch = inputs[offset : offset + batch_size]
        batches_attempted += 1
        if progress_callback is not None:
            progress_callback({
                "event": "batch_start",
                "batch_index": batches_attempted,
                "batch_count": (len(inputs) + batch_size - 1) // batch_size,
                "jobs": len(batch),
                "job_ids": [item.job_id for item in batch],
            })
        try:
            results = analyzer.analyze_batch(batch)
        except Exception as exc:
            if progress_callback is not None:
                progress_callback({
                    "event": "batch_failed",
                    "batch_index": batches_attempted,
                    "error": f"{type(exc).__name__}: {exc}",
                })
            failures += 1
            _record_batch_failure(engine, batch, str(exc))
            continue

        batch_model = str(getattr(analyzer, "last_model", analyzer.model))
        repaired_by = getattr(analyzer, "last_repaired_by", None)
        now = datetime.now(UTC)
        with Session(engine) as session, session.begin():
            by_id = {
                row.id: row
                for row in session.scalars(
                    select(SourceJob).where(SourceJob.id.in_([job.job_id for job in batch]))
                ).all()
            }
            input_by_id = {item.job_id: item for item in batch}
            for result in results:
                source = by_id[result.job_id]
                analysis_input = input_by_id[result.job_id]
                status = _analysis_status(result)
                analysis_model = (
                    batch_model
                    if not repaired_by
                    else f"{batch_model} [json_repair={repaired_by}]"
                )
                analysis_json = json.dumps(
                    result.model_dump(mode="json"),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                # The analysis version must be keyed by the effective input actually
                # sent to the model (detail-enriched fields included), not by the
                # listing/source payload hash.  Re-running the exact same input is
                # idempotent: update the existing row instead of violating the
                # unique version key.
                existing = session.scalar(
                    select(JobAiAnalysis).where(
                        JobAiAnalysis.source_job_row_id == source.id,
                        JobAiAnalysis.model == analysis_model,
                        JobAiAnalysis.prompt_version == analyzer.prompt_version,
                        JobAiAnalysis.schema_version == analyzer.schema_version,
                        JobAiAnalysis.input_payload_sha256 == analysis_input.payload_sha256,
                    )
                )
                if existing is None:
                    session.add(
                        JobAiAnalysis(
                            source_job_row_id=source.id,
                            analyzed_at=now,
                            model=analysis_model,
                            prompt_version=analyzer.prompt_version,
                            schema_version=analyzer.schema_version,
                            input_payload_sha256=analysis_input.payload_sha256,
                            is_cybersecurity=result.is_cybersecurity,
                            needs_more_detail=result.needs_more_detail,
                            valid=True,
                            analysis_json=analysis_json,
                            error=None,
                        )
                    )
                else:
                    existing.analyzed_at = now
                    existing.is_cybersecurity = result.is_cybersecurity
                    existing.needs_more_detail = result.needs_more_detail
                    existing.valid = True
                    existing.analysis_json = analysis_json
                    existing.error = None
                source.ai_status = status
                source.ai_attempts += 1
                source.ai_last_error = None
                source.ai_last_analyzed_at = now
                analyzed += 1
                cyber += int(status == "CYBER")
                non_cyber += int(status == "NON_CYBER")
                needs_detail += int(status == "NEEDS_MORE_DETAIL")
        batches_succeeded += 1
        if progress_callback is not None:
            progress_callback({
                "event": "batch_success",
                "batch_index": batches_attempted,
                "model": batch_model,
                "jobs": len(results),
            })

    with Session(engine) as session:
        pending_statement = select(SourceJob.id).where(
            SourceJob.ai_status == "PENDING_AI", SourceJob.is_active.is_(True)
        )
        if portal_ids is not None:
            pending_statement = pending_statement.where(SourceJob.portal_id.in_(portal_ids))
        pending = len(session.scalars(pending_statement).all())

    return AnalyzePendingSummary(
        selected_jobs=len(inputs),
        batches_attempted=batches_attempted,
        batches_succeeded=batches_succeeded,
        api_failures=failures,
        analyzed_jobs=analyzed,
        cyber_jobs=cyber,
        non_cyber_jobs=non_cyber,
        needs_more_detail_jobs=needs_detail,
        still_pending_jobs=pending,
    )


def preview_pending_jobs(
    engine: Engine, *, limit: int, portal_ids: set[int] | None = None
) -> list[AnalysisInput]:
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
        return [_analysis_input(row) for row in rows]


def preview_semantic_cleanup_candidates(
    engine: Engine,
    *,
    limit: int = 100,
    min_description_chars: int = SUBSTANTIVE_DESCRIPTION_CHARS,
) -> list[SemanticCleanupCandidate]:
    """Find persisted states that violate the current semantic contract.

    This is intentionally narrow rather than a blanket prompt-version migration.
    The cyber-job-v3 contract changed one material behavior: a substantive job
    description must receive a binary CYBER/NON_CYBER decision.  Re-analyzing every
    historical row after that prompt bump would waste free-provider quota, so only
    NEEDS_MORE_DETAIL rows that already have sufficient evidence are requeued.
    """

    if limit < 1:
        raise ValueError("limit must be >= 1")
    if min_description_chars < 1:
        raise ValueError("min_description_chars must be >= 1")
    create_schema(engine)
    with Session(engine) as session:
        rows = session.scalars(
            select(SourceJob)
            .where(
                SourceJob.ai_status == "NEEDS_MORE_DETAIL",
                SourceJob.is_active.is_(True),
            )
            .order_by(SourceJob.id)
        ).all()
        candidates: list[SemanticCleanupCandidate] = []
        for row in rows:
            analysis_input = _analysis_input(row)
            description_chars = len(analysis_input.description.strip())
            if description_chars < min_description_chars:
                continue
            candidates.append(
                SemanticCleanupCandidate(
                    job_id=row.id,
                    company=analysis_input.company,
                    title=analysis_input.title,
                    description_chars=description_chars,
                    current_status=row.ai_status,
                )
            )
            if len(candidates) >= limit:
                break
        return candidates


def requeue_semantic_cleanup_candidates(
    engine: Engine,
    *,
    limit: int = 100,
    min_description_chars: int = SUBSTANTIVE_DESCRIPTION_CHARS,
) -> SemanticCleanupSummary:
    """Requeue only contract-inconsistent, fully-described NEEDS_MORE_DETAIL rows."""

    candidates = preview_semantic_cleanup_candidates(
        engine,
        limit=limit,
        min_description_chars=min_description_chars,
    )
    if not candidates:
        return SemanticCleanupSummary(selected_jobs=0, requeued_jobs=0)
    ids = [item.job_id for item in candidates]
    with Session(engine) as session, session.begin():
        rows = session.scalars(select(SourceJob).where(SourceJob.id.in_(ids))).all()
        for row in rows:
            row.ai_status = "PENDING_AI"
            row.ai_last_error = None
    return SemanticCleanupSummary(selected_jobs=len(candidates), requeued_jobs=len(ids))


def _analysis_input(row: SourceJob) -> AnalysisInput:
    company = row.resolved_company_name or row.raw_company
    title = row.detail_title or row.raw_title
    location = row.detail_location or row.raw_location
    country = row.detail_country or row.raw_country
    city = row.detail_city or row.raw_city
    employment_type = row.detail_employment_type or row.raw_employment_type
    workplace_type = row.detail_workplace_type or row.raw_workplace_type
    description = row.detail_description or row.raw_description
    source_url = row.detail_url or row.source_url
    effective = {
        "company": company,
        "title": title,
        "location": location,
        "country": country,
        "city": city,
        "employment_type": employment_type,
        "workplace_type": workplace_type,
        "description": description,
        "source_url": source_url,
    }
    effective_json = json.dumps(
        effective, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return AnalysisInput(
        job_id=row.id,
        company=company,
        title=title,
        location=location,
        country=country,
        city=city,
        employment_type=employment_type,
        workplace_type=workplace_type,
        description=description,
        source_url=source_url,
        payload_sha256=hashlib.sha256(effective_json.encode("utf-8")).hexdigest(),
    )


def _analysis_status(result: JobAnalysis) -> str:
    if result.needs_more_detail or result.is_cybersecurity is None:
        return "NEEDS_MORE_DETAIL"
    return "CYBER" if result.is_cybersecurity else "NON_CYBER"


def _record_batch_failure(engine: Engine, batch: list[AnalysisInput], error: str) -> None:
    with Session(engine) as session, session.begin():
        rows = session.scalars(
            select(SourceJob).where(SourceJob.id.in_([item.job_id for item in batch]))
        ).all()
        for row in rows:
            row.ai_attempts += 1
            row.ai_last_error = error[:4000]
            # Keep PENDING_AI: a later manual run can retry without re-scanning the portal.


def _validate_batch_ids(inputs: list[AnalysisInput], outputs: list[JobAnalysis]) -> None:
    expected = [item.job_id for item in inputs]
    actual = [item.job_id for item in outputs]
    if len(actual) != len(set(actual)):
        raise ValueError("LLM returned duplicate job_id values")
    if set(expected) != set(actual):
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        raise ValueError(f"LLM batch ID mismatch: missing={missing} extra={extra}")



def _validate_semantic_completeness(
    inputs: list[AnalysisInput], outputs: list[JobAnalysis]
) -> None:
    """Reject contradictory NEEDS_MORE_DETAIL answers when full evidence was supplied.

    This does not classify the job deterministically. It only enforces the LLM contract:
    once a substantial description is available, the semantic model must make the
    CYBER/NON_CYBER decision instead of asking the crawler for data it already has.
    """

    by_id = {item.job_id: item for item in inputs}
    contradictions: list[int] = []
    for result in outputs:
        source = by_id[result.job_id]
        if len(source.description.strip()) < SUBSTANTIVE_DESCRIPTION_CHARS:
            continue
        if result.needs_more_detail or result.is_cybersecurity is None:
            contradictions.append(result.job_id)
    if contradictions:
        raise ValueError(
            "LLM requested more detail despite substantive descriptions for job_ids="
            f"{sorted(contradictions)}; make a CYBER/NON_CYBER decision"
        )

def _bounded_description(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    # Requirements often live near the end; preserve both beginning and tail.
    head = max_chars * 2 // 3
    tail = max_chars - head
    return value[:head] + "\n...[truncated for model input only]...\n" + value[-tail:]
