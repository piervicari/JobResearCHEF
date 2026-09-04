from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_agent.db.migrations import create_schema
from research_agent.db.models import (
    ClusterPortalMapping,
    CorporateCluster,
    ImportBatch,
    Portal,
    ScanRun,
    SourceJob,
)
from research_agent.pipeline.detail_enrichment import (
    _collapse_apply_path,
    _detail_request_url,
    parse_detail_html,
    select_detail_candidates,
)


def _seed_workday_portal(
    engine: Engine,
    *,
    portal_id: int,
    cluster_id: str,
    host: str = "nvidia.wd5.myworkdayjobs.com",
    jobs_search_url: str | None = None,
    sha_marker: str = "wd",
) -> None:
    """Create one CorporateCluster + one Portal + one ClusterPortalMapping
    so candidate selection can run without a master-import dependency."""
    if jobs_search_url is None:
        jobs_search_url = f"https://{host}/NVIDIAExternalCareerSite"
    with Session(engine) as session, session.begin():
        batch = ImportBatch(
            source_kind="test",
            source_filename=f"loader-fixture-{sha_marker}.csv",
            source_path=f"loader-fixture-{sha_marker}.csv",
            source_sha256=("a" * 60) + sha_marker.ljust(4, "a"),
            source_version=f"loader-fixture-{sha_marker}-v1",
            status="COMPLETE",
        )
        session.add(batch)
        session.flush()
        session.add(
            CorporateCluster(
                corporate_cluster_id=cluster_id,
                representative_canonical_employer="NVIDIA",
                canonical_employers_json="[\"NVIDIA\"]",
                parent_groups_json="[]",
                entity_classes_json="[]",
                eligibility_values_json="[]",
                sectors_json="[]",
                discovery_geographies_json="[]",
                org_types_json="[]",
                record_count=1,
                has_primary_scan_eligibility=True,
                import_batch_id=batch.id,
            )
        )
        portal = Portal(
            id=portal_id,
            normalized_jobs_url=jobs_search_url,
            jobs_search_url=jobs_search_url,
            scheme="https",
            host=host,
            ats_families_json="[\"Workday\"]",
            ats_confidences_json="[\"Verified\"]",
            metadata_conflict=False,
            cluster_count=1,
            active_in_registry=True,
            health_state="HEALTHY",
            consecutive_failures=0,
            scan_enabled=False,
            import_batch_id=batch.id,
        )
        session.add(portal)
        session.flush()
        session.add(
            ClusterPortalMapping(
                corporate_cluster_id=cluster_id,
                portal_id=portal.id,
                resolved_corporate_website="https://nvidia.com",
                resolved_careers_landing_url=jobs_search_url,
                source_jobs_search_url=jobs_search_url,
                portal_scope="Global",
                ats_family="Workday",
                ats_confidence="Verified",
                portal_resolution_status="VERIFIED",
                portal_verification_url=jobs_search_url,
                portal_verified_date=date(2026, 5, 1),
                resolution_wave="W1",
                source_record_count=1,
                import_batch_id=batch.id,
            )
        )


def _add_source_job(
    engine: Engine,
    *,
    portal_id: int,
    raw_title: str,
    source_url: str,
    raw_description: str = "",
    ai_status: str = "NEEDS_MORE_DETAIL",
    adapter: str = "workday",
) -> int:
    with Session(engine) as session, session.begin():
        # Minimal ScanRun so the FK on SourceJob.scan_run_id is satisfied.
        run = ScanRun(
            source="test_fixture",
            status="COMPLETED",
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            portal_count=1,
            success_count=1,
            failure_count=0,
            jobs_discovered=1,
            pipeline_status="NOT_PROCESSED",
        )
        session.add(run)
        session.flush()
        row = SourceJob(
            scan_run_id=run.id,
            portal_id=portal_id,
            canonical_job_id=None,
            source=adapter,
            source_job_id=source_url.rsplit("/", 1)[-1],
            source_url=source_url,
            apply_url=source_url,
            canonical_apply_url=source_url,
            raw_title=raw_title,
            raw_company="NVIDIA",
            resolved_corporate_cluster_id="CG-NVIDIA",
            resolved_company_name="NVIDIA",
            raw_description=raw_description,
            fetched_at=datetime.now(UTC),
            adapter=adapter,
            parser_version="0.1.0",
            payload_sha256="0" * 64,
            raw_payload_json="{}",
            first_seen_at=datetime.now(UTC),
            last_seen_at=datetime.now(UTC),
            is_active=True,
            missing_successful_scans=0,
            ai_status=ai_status,
        )
        session.add(row)
        session.flush()
        return row.id


def test_parse_detail_html_prefers_jobposting_json_ld():
    html = '''
    <html><body><script type="application/ld+json">
    {
      "@context":"https://schema.org",
      "@type":"JobPosting",
      "title":"Threat Intelligence Analyst",
      "description":"<p>Investigate threats and produce intelligence.</p>",
      "employmentType":"FULL_TIME",
      "jobLocation":{"@type":"Place","address":{"@type":"PostalAddress","addressLocality":"Rome","addressCountry":"IT"}}
    }
    </script></body></html>
    '''
    parsed = parse_detail_html(html, final_url="https://example.test/job/1")
    assert parsed.title == "Threat Intelligence Analyst"
    assert "Investigate threats" in parsed.description
    assert parsed.city == "Rome"
    assert parsed.country == "IT"
    assert parsed.parser == "json_ld_jobposting"


def test_parse_detail_html_falls_back_to_main_text_and_labels():
    html = '''
    <html><body><main>
      <div>Security · Stockholm · Hybrid</div>
      <h1>Cyber Security Solutions Engineer</h1>
      <p>Work with customers on application security and vulnerability findings.</p>
      <h2>Locations</h2><div>Stockholm</div>
      <h2>Employment type</h2><div>Full-time</div>
    </main></body></html>
    '''
    parsed = parse_detail_html(html, final_url="https://example.test/jobs/1")
    assert parsed.title == "Cyber Security Solutions Engineer"
    assert parsed.location == "Stockholm"
    assert parsed.employment_type == "Full-time"
    assert "application security" in parsed.description
    assert parsed.parser == "main_text"


def test_workday_apply_url_is_appended_once():
    src = "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/India-Pune/SWE_JR2018442-1"
    assert _detail_request_url(src, "workday") == src.rstrip("/") + "/apply"


def test_workday_apply_url_idempotent_when_already_present():
    src = "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/SWE_JR1/apply"
    assert _detail_request_url(src, "workday") == src
    # And if it somehow has /apply twice, the defensive collapse brings it back.
    doubled = src + "/apply"
    assert _collapse_apply_path(doubled) == src


def test_official_html_url_is_not_appended():
    src = "https://example.com/careers/job/1"
    assert _detail_request_url(src, "official_html") == src
    assert _detail_request_url(src.rstrip("/") + "/", "official_html") == src


def test_workday_candidate_is_selected_and_request_url_uses_apply(
    sqlite_engine: Engine,
) -> None:
    create_schema(sqlite_engine)
    _seed_workday_portal(sqlite_engine, portal_id=539, cluster_id="CG-NVIDIA")
    job_id = _add_source_job(
        sqlite_engine,
        portal_id=539,
        raw_title="Software Solutions Engineer",
        source_url=(
            "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"
            "/job/India-Pune/SWE_JR2018442-1"
        ),
    )
    candidates = select_detail_candidates(
        sqlite_engine, limit=5, min_description_chars=500
    )
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.job_id == job_id
    assert candidate.request_url == (
        "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"
        "/job/India-Pune/SWE_JR2018442-1/apply"
    )
    assert candidate.request_url.endswith("/apply")
    assert candidate.request_url.count("/apply") == 1


def test_official_html_candidate_keeps_its_original_url(
    sqlite_engine: Engine,
) -> None:
    create_schema(sqlite_engine)
    with Session(sqlite_engine) as session, session.begin():
        batch = ImportBatch(
            source_kind="test", source_filename="oh-fixture", source_path="oh-fixture",
            source_sha256=("b" * 60) + "ohpl".ljust(4, "b"),
            source_version="oh-v1", status="COMPLETE",
        )
        session.add(batch)
        session.flush()
        session.add(
            CorporateCluster(
                corporate_cluster_id="CG-OH",
                representative_canonical_employer="OH",
                canonical_employers_json="[\"OH\"]",
                parent_groups_json="[]",
                entity_classes_json="[]",
                eligibility_values_json="[]",
                sectors_json="[]",
                discovery_geographies_json="[]",
                org_types_json="[]",
                record_count=1,
                has_primary_scan_eligibility=True,
                import_batch_id=batch.id,
            )
        )
        portal = Portal(
            id=42,
            normalized_jobs_url="https://oh.example.test/jobs",
            jobs_search_url="https://oh.example.test/jobs",
            scheme="https",
            host="oh.example.test",
            ats_families_json="[\"Custom\"]",
            ats_confidences_json="[\"Verified\"]",
            metadata_conflict=False,
            cluster_count=1,
            active_in_registry=True,
            health_state="HEALTHY",
            consecutive_failures=0,
            scan_enabled=True,
            import_batch_id=batch.id,
        )
        session.add(portal)
        session.flush()
        session.add(
            ClusterPortalMapping(
                corporate_cluster_id="CG-OH",
                portal_id=portal.id,
                resolved_corporate_website="https://oh.example.test",
                resolved_careers_landing_url="https://oh.example.test/jobs",
                source_jobs_search_url="https://oh.example.test/jobs",
                portal_scope="Global",
                ats_family="Custom",
                ats_confidence="Verified",
                portal_resolution_status="VERIFIED",
                portal_verification_url="https://oh.example.test/jobs",
                portal_verified_date=date(2026, 5, 1),
                resolution_wave="W1",
                source_record_count=1,
                import_batch_id=batch.id,
            )
        )
    _add_source_job(
        sqlite_engine,
        portal_id=42,
        raw_title="Junior AppSec",
        source_url="https://oh.example.test/jobs/junior-appsec-1",
        adapter="official_html",
    )
    candidates = select_detail_candidates(
        sqlite_engine, limit=5, min_description_chars=500
    )
    assert len(candidates) == 1
    assert candidates[0].request_url == "https://oh.example.test/jobs/junior-appsec-1"
    # No /apply appended for official_html.
    assert "/apply" not in candidates[0].request_url


def test_workday_candidate_rejected_when_source_url_changes_host(
    sqlite_engine: Engine,
) -> None:
    create_schema(sqlite_engine)
    _seed_workday_portal(sqlite_engine, portal_id=539, cluster_id="CG-NVIDIA")
    # source_url points to a different host (e.g. a tracking redirect) — must be
    # rejected because the detail fetch is forced onto the same host as the portal.
    _add_source_job(
        sqlite_engine,
        portal_id=539,
        raw_title="SWE",
        source_url=(
            "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"
            "/job/SWE_JR1/apply"
        ),
    )
    # Override the apply URL with a foreign host via direct DB edit.
    with Session(sqlite_engine) as session:
        row = session.scalar(select(SourceJob))
        assert row is not None
        row.source_url = "https://tracking.example.test/redirect/JR1"
        session.commit()
    # After the change, candidate selection must skip the row because the
    # resulting /apply URL host does not match the portal host.
    candidates = select_detail_candidates(
        sqlite_engine, limit=5, min_description_chars=500
    )
    assert candidates == []


def test_workday_already_applied_url_is_not_double_suffixed(
) -> None:
    src = "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/SWE_JR1/apply"
    out = _detail_request_url(src, "workday")
    assert out == src
    assert out.count("/apply") == 1


def test_portal_filter_restricts_candidate_set(sqlite_engine: Engine) -> None:
    """`enrich-details --portal-id X` should not touch other employers."""
    create_schema(sqlite_engine)
    _seed_workday_portal(
        sqlite_engine, portal_id=539, cluster_id="CG-NVIDIA",
        host="nvidia.wd5.myworkdayjobs.com",
        sha_marker="wd_a",
    )
    # Seed a second Workday portal for a different cluster.
    _seed_workday_portal(
        sqlite_engine, portal_id=265, cluster_id="CG-PROOFPOINT",
        host="proofpoint.wd5.myworkdayjobs.com",
        jobs_search_url="https://proofpoint.wd5.myworkdayjobs.com/proofpointcareers",
        sha_marker="wd_b",
    )
    nvidia_id = _add_source_job(
        sqlite_engine,
        portal_id=539,
        raw_title="NVIDIA SWE",
        source_url=(
            "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"
            "/job/SWE_JR1"
        ),
    )
    proofpoint_id = _add_source_job(
        sqlite_engine,
        portal_id=265,
        raw_title="Proofpoint Engineer",
        source_url=(
            "https://proofpoint.wd5.myworkdayjobs.com/proofpointcareers"
            "/job/Eng_JR2"
        ),
    )
    # No filter: both candidates come back (subject to per-host cap).
    all_candidates = select_detail_candidates(
        sqlite_engine, limit=10, min_description_chars=500, max_jobs_per_host=1
    )
    assert {c.job_id for c in all_candidates} == {nvidia_id, proofpoint_id}
    # Filter to NVIDIA only.
    nvidia_only = select_detail_candidates(
        sqlite_engine,
        limit=10,
        min_description_chars=500,
        max_jobs_per_host=1,
        portal_ids={539},
    )
    assert [c.job_id for c in nvidia_only] == [nvidia_id]
    # Empty portal_ids set must return no candidates.
    empty = select_detail_candidates(
        sqlite_engine,
        limit=10,
        min_description_chars=500,
        max_jobs_per_host=1,
        portal_ids=set(),
    )
    assert empty == []


def test_workday_json_ld_parses_via_existing_parse_detail_html() -> None:
    """End-to-end shape check: a Workday /apply HTML body — which is a React
    SPA — does NOT contain a parseable main_text, but it DOES carry a
    single `<script type="application/ld+json">` JobPosting. The existing
    `parse_detail_html` must therefore yield `parser="json_ld_jobposting"`
    with the full description and metadata, without any new Workday
    parser/regex being added."""
    html = '''<html><head><title>Software Solutions Engineer</title></head><body><div id="root"></div><script type="application/ld+json">{"@context":"https://schema.org","@type":"JobPosting","title":"Software Solutions Engineer","description":"<p>Investigate complex customer software issues and build automation across cloud and datacenter environments. The role combines customer-facing support with internal software engineering.</p>","employmentType":"FULL_TIME","jobLocation":{"@type":"Place","address":{"@type":"PostalAddress","addressLocality":"Pune","addressCountry":"India"}},"hiringOrganization":{"name":"NVIDIA","@type":"Organization"},"datePosted":"2026-09-04"}</script></body></html>'''
    parsed = parse_detail_html(
        html,
        final_url=(
            "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"
            "/job/India-Pune/SWE_JR2018442-1/apply"
        ),
    )
    assert parsed.parser == "json_ld_jobposting"
    assert parsed.title == "Software Solutions Engineer"
    assert "Investigate complex customer software issues" in parsed.description
    assert parsed.country == "India"
    assert parsed.city == "Pune"
    assert parsed.employment_type == "FULL_TIME"
    assert parsed.detail_url.endswith("/apply")
