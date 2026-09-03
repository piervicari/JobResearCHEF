from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_agent.ai.job_analyzer import AnalysisInput, analyze_pending_jobs
from research_agent.ai.schema import JobAnalysis
from research_agent.db.migrations import create_schema
from research_agent.db.models import JobAiAnalysis, ScanRun, SourceJob


class FakeAnalyzer:
    model = "fake/model"
    prompt_version = "test-prompt"
    schema_version = "test-schema"

    def analyze_batch(self, jobs: list[AnalysisInput]) -> list[JobAnalysis]:
        return [
            JobAnalysis(
                job_id=job.job_id,
                is_cybersecurity=(index == 0),
                needs_more_detail=False,
                role_family="Security Engineering" if index == 0 else None,
                seniority="senior" if index == 0 else "mid",
                skills_required=["Python"] if index == 0 else [],
            )
            for index, job in enumerate(jobs)
        ]


class FailingAnalyzer(FakeAnalyzer):
    def analyze_batch(self, jobs: list[AnalysisInput]) -> list[JobAnalysis]:
        raise RuntimeError("temporary provider failure")


def _seed_pending(engine: Engine, count: int = 2) -> list[int]:
    create_schema(engine)
    now = datetime.now(UTC)
    with Session(engine) as session, session.begin():
        run = ScanRun(source="test", status="COMPLETED", started_at=now, finished_at=now)
        session.add(run)
        session.flush()
        ids = []
        for index in range(count):
            row = SourceJob(
                scan_run_id=run.id,
                portal_id=None,
                canonical_job_id=None,
                source="fixture",
                source_job_id=f"job-{index}",
                native_source_job_id=f"job-{index}",
                source_url=f"https://example.test/job-{index}",
                apply_url=f"https://example.test/job-{index}/apply",
                canonical_apply_url=f"https://example.test/job-{index}/apply",
                ats_job_id=f"ats-{index}",
                requisition_id=f"req-{index}",
                raw_title="Security Engineer" if index == 0 else "Accountant",
                raw_company="Example",
                resolved_corporate_cluster_id="",
                resolved_company_name="Example",
                raw_location="Milan, Italy",
                raw_country="IT",
                raw_city="Milan",
                raw_employment_type="FullTime",
                raw_workplace_type="hybrid",
                raw_description="Analyze security threats." if index == 0 else "Prepare accounts.",
                posted_at=None,
                fetched_at=now,
                adapter="fixture",
                parser_version="0.2.0",
                payload_sha256=(str(index) * 64)[:64],
                raw_payload_json="{}",
                first_seen_at=now,
                last_seen_at=now,
                is_active=True,
                missing_successful_scans=0,
                ai_status="PENDING_AI",
                ai_attempts=0,
            )
            session.add(row)
            session.flush()
            ids.append(row.id)
        return ids


def test_analyze_pending_updates_queue_and_stores_versioned_results(sqlite_engine: Engine) -> None:
    ids = _seed_pending(sqlite_engine)
    summary = analyze_pending_jobs(sqlite_engine, FakeAnalyzer(), limit=10, batch_size=2)

    assert summary.analyzed_jobs == 2
    assert summary.cyber_jobs == 1
    assert summary.non_cyber_jobs == 1
    assert summary.api_failures == 0
    with Session(sqlite_engine) as session:
        rows = session.scalars(select(SourceJob).order_by(SourceJob.id)).all()
        assert [row.ai_status for row in rows] == ["CYBER", "NON_CYBER"]
        assert all(row.ai_attempts == 1 for row in rows)
        analyses = session.scalars(select(JobAiAnalysis).order_by(JobAiAnalysis.id)).all()
        assert len(analyses) == 2
        assert {row.source_job_row_id for row in analyses} == set(ids)
        assert all(row.input_payload_sha256 for row in analyses)


def test_failed_batch_stays_pending_without_network_rescan(sqlite_engine: Engine) -> None:
    _seed_pending(sqlite_engine, count=1)
    summary = analyze_pending_jobs(sqlite_engine, FailingAnalyzer(), limit=1, batch_size=1)

    assert summary.api_failures == 1
    assert summary.analyzed_jobs == 0
    with Session(sqlite_engine) as session:
        source = session.scalar(select(SourceJob))
        assert source is not None
        assert source.ai_status == "PENDING_AI"
        assert source.ai_attempts == 1
        assert "temporary provider failure" in (source.ai_last_error or "")
        assert session.scalar(select(JobAiAnalysis)) is None


def test_analysis_input_prefers_detail_enrichment_and_hashes_effective_input(sqlite_engine: Engine) -> None:
    _seed_pending(sqlite_engine, count=1)
    from research_agent.ai.job_analyzer import preview_pending_jobs

    before = preview_pending_jobs(sqlite_engine, limit=1)[0]
    with Session(sqlite_engine) as session, session.begin():
        source = session.scalar(select(SourceJob))
        assert source is not None
        source.detail_title = "Application Security Engineer"
        source.detail_location = "Turin, Italy"
        source.detail_country = "IT"
        source.detail_city = "Turin"
        source.detail_description = "Full official detail description with AppSec responsibilities."
        source.detail_url = "https://example.test/job-0/detail"
    after = preview_pending_jobs(sqlite_engine, limit=1)[0]

    assert after.title == "Application Security Engineer"
    assert after.location == "Turin, Italy"
    assert after.city == "Turin"
    assert after.description.startswith("Full official detail")
    assert after.source_url.endswith("/detail")
    assert after.payload_sha256 != before.payload_sha256


def test_substantive_description_cannot_remain_needs_more_detail() -> None:
    from research_agent.ai.job_analyzer import _validate_semantic_completeness

    source = AnalysisInput(
        job_id=101,
        company="Detectify",
        title="Senior Cloud Engineer",
        location="Stockholm, SE",
        country="SE",
        city="Stockholm",
        employment_type="Full-time",
        workplace_type="hybrid",
        description=("Core cloud engineering responsibilities. Security is only a nice-to-have. " * 30),
        source_url="https://example.test/jobs/101",
        payload_sha256="a" * 64,
    )
    ambiguous = JobAnalysis(
        job_id=101,
        is_cybersecurity=None,
        needs_more_detail=True,
        short_reason="The role is primarily cloud engineering; security is incidental.",
    )

    import pytest

    with pytest.raises(ValueError, match="substantive descriptions"):
        _validate_semantic_completeness([source], [ambiguous])


def test_short_description_may_still_request_more_detail() -> None:
    from research_agent.ai.job_analyzer import _validate_semantic_completeness

    source = AnalysisInput(
        job_id=102,
        company="Wazuh",
        title="DevOps Engineer",
        location="Remote",
        country="",
        city="",
        employment_type="",
        workplace_type="remote",
        description="",
        source_url="https://example.test/jobs/102",
        payload_sha256="b" * 64,
    )
    ambiguous = JobAnalysis(job_id=102, is_cybersecurity=None, needs_more_detail=True)

    _validate_semantic_completeness([source], [ambiguous])


def test_detail_reanalysis_uses_effective_input_hash_not_source_payload_hash(sqlite_engine: Engine) -> None:
    _seed_pending(sqlite_engine, count=1)
    first = analyze_pending_jobs(sqlite_engine, FakeAnalyzer(), limit=1, batch_size=1)
    assert first.analyzed_jobs == 1

    with Session(sqlite_engine) as session, session.begin():
        source = session.scalar(select(SourceJob))
        assert source is not None
        original_source_hash = source.payload_sha256
        source.detail_title = "Application Security Engineer"
        source.detail_location = "Turin, Italy"
        source.detail_description = "Application security responsibilities and threat modeling. " * 30
        source.detail_url = "https://example.test/job-0/detail"
        source.ai_status = "PENDING_AI"

    second = analyze_pending_jobs(sqlite_engine, FakeAnalyzer(), limit=1, batch_size=1)
    assert second.analyzed_jobs == 1

    with Session(sqlite_engine) as session:
        source = session.scalar(select(SourceJob))
        analyses = session.scalars(select(JobAiAnalysis).order_by(JobAiAnalysis.id)).all()
        assert source is not None
        assert source.payload_sha256 == original_source_hash
        assert len(analyses) == 2
        assert analyses[0].input_payload_sha256 != analyses[1].input_payload_sha256
        assert all(row.input_payload_sha256 != original_source_hash for row in analyses)


def test_exact_same_ai_input_is_idempotent_instead_of_unique_constraint_crash(sqlite_engine: Engine) -> None:
    _seed_pending(sqlite_engine, count=1)
    first = analyze_pending_jobs(sqlite_engine, FakeAnalyzer(), limit=1, batch_size=1)
    assert first.analyzed_jobs == 1

    with Session(sqlite_engine) as session, session.begin():
        source = session.scalar(select(SourceJob))
        assert source is not None
        source.ai_status = "PENDING_AI"

    second = analyze_pending_jobs(sqlite_engine, FakeAnalyzer(), limit=1, batch_size=1)
    assert second.analyzed_jobs == 1

    with Session(sqlite_engine) as session:
        source = session.scalar(select(SourceJob))
        analyses = session.scalars(select(JobAiAnalysis)).all()
        assert source is not None
        assert source.ai_attempts == 2
        assert len(analyses) == 1


def test_semantic_cleanup_requeues_only_fully_described_needs_more_detail(sqlite_engine: Engine) -> None:
    from research_agent.ai.job_analyzer import (
        preview_semantic_cleanup_candidates,
        requeue_semantic_cleanup_candidates,
    )

    ids = _seed_pending(sqlite_engine, count=3)
    with Session(sqlite_engine) as session, session.begin():
        rows = session.scalars(select(SourceJob).order_by(SourceJob.id)).all()
        rows[0].ai_status = "NEEDS_MORE_DETAIL"
        rows[0].detail_description = "Cloud engineering core role; security is incidental. " * 30
        rows[1].ai_status = "NEEDS_MORE_DETAIL"
        rows[1].detail_description = "short"
        rows[2].ai_status = "NON_CYBER"
        rows[2].detail_description = "Substantive non-cyber description. " * 50

    candidates = preview_semantic_cleanup_candidates(sqlite_engine, limit=10)
    assert [row.job_id for row in candidates] == [ids[0]]
    assert candidates[0].description_chars >= 1000

    summary = requeue_semantic_cleanup_candidates(sqlite_engine, limit=10)
    assert summary.selected_jobs == 1
    assert summary.requeued_jobs == 1

    with Session(sqlite_engine) as session:
        rows = session.scalars(select(SourceJob).order_by(SourceJob.id)).all()
        assert rows[0].ai_status == "PENDING_AI"
        assert rows[1].ai_status == "NEEDS_MORE_DETAIL"
        assert rows[2].ai_status == "NON_CYBER"


def test_full_analysis_prompt_excludes_financial_risk_and_fraud_operations() -> None:
    from research_agent.ai.job_analyzer import RoutedJobAnalyzer

    prompt = RoutedJobAnalyzer.SYSTEM_PROMPT
    assert "payment or merchant fraud operations" in prompt.lower()
    assert "AML" in prompt
    assert "Enterprise Risk Management -> NON_CYBER" in prompt
    assert "Security GRC -> CYBER" in prompt
