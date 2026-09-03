from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_agent.ai.job_triage import JobTriageDecision, triage_pending_jobs
from research_agent.db.migrations import create_schema
from research_agent.db.models import JobAiAnalysis, ScanRun, SourceJob


class FakeTriageAnalyzer:
    last_model = "openrouter/minimax/minimax-m3:free"
    last_repaired_by = None
    prompt_version = "cyber-triage-test"
    schema_version = "job-triage-test"

    def analyze_batch(self, jobs):
        return [
            JobTriageDecision(
                job_id=item.job_id,
                candidate_cyber=("Sales" not in item.title),
                short_reason="candidate" if "Sales" not in item.title else "clear sales role",
            )
            for item in jobs
        ]


def _seed(engine: Engine) -> list[int]:
    create_schema(engine)
    now = datetime.now(UTC)
    with Session(engine) as session, session.begin():
        run = ScanRun(source="triage-test", status="COMPLETED", started_at=now, finished_at=now)
        session.add(run)
        session.flush()
        ids = []
        for idx, title in enumerate(("Security Engineer", "Sales Manager")):
            row = SourceJob(
                scan_run_id=run.id,
                portal_id=None,
                canonical_job_id=None,
                source="fixture",
                source_job_id=f"triage-{idx}",
                native_source_job_id=f"triage-{idx}",
                source_url=f"https://example.test/{idx}",
                apply_url=f"https://example.test/{idx}",
                canonical_apply_url=f"https://example.test/{idx}",
                raw_title=title,
                raw_company="Example",
                resolved_corporate_cluster_id="",
                resolved_company_name="Example",
                raw_location="Remote",
                raw_country="",
                raw_city="",
                raw_employment_type="",
                raw_workplace_type="remote",
                raw_description="Detailed responsibilities " * 100,
                fetched_at=now,
                adapter="fixture",
                parser_version="0.2.0",
                payload_sha256=(str(idx + 1) * 64)[:64],
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


def test_triage_only_removes_clear_non_cyber_and_keeps_candidates_pending(sqlite_engine: Engine) -> None:
    ids = _seed(sqlite_engine)
    summary = triage_pending_jobs(
        sqlite_engine,
        FakeTriageAnalyzer(),
        limit=10,
        batch_size=100,
    )
    assert summary.selected_jobs == 2
    assert summary.obvious_non_cyber == 1
    assert summary.candidates_for_full_analysis == 1
    with Session(sqlite_engine) as session:
        rows = session.scalars(select(SourceJob).order_by(SourceJob.id)).all()
        assert [row.ai_status for row in rows] == ["PENDING_AI", "NON_CYBER"]
        analyses = session.scalars(select(JobAiAnalysis).order_by(JobAiAnalysis.id)).all()
        assert len(analyses) == 2
        assert all(row.model.startswith("triage:") for row in analyses)
        assert {row.source_job_row_id for row in analyses} == set(ids)


def test_triage_prompt_keeps_high_recall_but_excludes_clear_financial_crime_roles() -> None:
    from research_agent.ai.job_triage import RoutedJobTriageAnalyzer

    prompt = RoutedJobTriageAnalyzer.SYSTEM_PROMPT
    assert "payment/merchant fraud operations" in prompt
    assert "AML" in prompt
    assert "Security GRC" in prompt
    assert "generic enterprise or operational risk" in prompt
