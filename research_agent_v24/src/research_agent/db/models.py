"""Relational data model for the company, portal and vacancy layers."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class ImportBatch(Base):
    """Audit record for an immutable source import."""

    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    source_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="RUNNING")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    row_count: Mapped[int | None] = mapped_column(Integer)
    cluster_count: Mapped[int | None] = mapped_column(Integer)
    resolved_row_count: Mapped[int | None] = mapped_column(Integer)
    resolved_cluster_count: Mapped[int | None] = mapped_column(Integer)
    portal_count: Mapped[int | None] = mapped_column(Integer)
    validation_json: Mapped[str | None] = mapped_column(Text)


class CorporateCluster(Base):
    """Stable company identity; multi-valued attributes remain explicitly aggregated."""

    __tablename__ = "corporate_clusters"

    corporate_cluster_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    representative_canonical_employer: Mapped[str] = mapped_column(String(500), nullable=False)
    canonical_employers_json: Mapped[str] = mapped_column(Text, nullable=False)
    parent_groups_json: Mapped[str] = mapped_column(Text, nullable=False)
    entity_classes_json: Mapped[str] = mapped_column(Text, nullable=False)
    eligibility_values_json: Mapped[str] = mapped_column(Text, nullable=False)
    sectors_json: Mapped[str] = mapped_column(Text, nullable=False)
    discovery_geographies_json: Mapped[str] = mapped_column(Text, nullable=False)
    org_types_json: Mapped[str] = mapped_column(Text, nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    has_primary_scan_eligibility: Mapped[bool] = mapped_column(Boolean, nullable=False)
    active_in_master: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    import_batch_id: Mapped[int] = mapped_column(
        ForeignKey("import_batches.id", ondelete="RESTRICT"), nullable=False
    )

    records: Mapped[list[CompanyRecord]] = relationship(back_populates="cluster")
    portal_mappings: Mapped[list[ClusterPortalMapping]] = relationship(back_populates="cluster")
    canonical_jobs: Mapped[list[CanonicalJob]] = relationship(back_populates="cluster")
    aliases: Mapped[list[CompanyAlias]] = relationship(back_populates="cluster")


class CompanyAlias(Base):
    """Reviewed external company name; only VERIFIED rows may resolve jobs."""

    __tablename__ = "company_aliases"
    __table_args__ = (
        UniqueConstraint(
            "normalized_alias",
            "corporate_cluster_id",
            name="uq_company_alias_cluster",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alias: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    corporate_cluster_id: Mapped[str] = mapped_column(
        ForeignKey("corporate_clusters.corporate_cluster_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    provenance: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_reference: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    import_batch_id: Mapped[int] = mapped_column(
        ForeignKey("import_batches.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    cluster: Mapped[CorporateCluster] = relationship(back_populates="aliases")


class CompanyRecord(Base):
    """One source row from the authoritative master, preserved without lossy merging."""

    __tablename__ = "company_records"

    record_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    import_batch_id: Mapped[int] = mapped_column(
        ForeignKey("import_batches.id", ondelete="RESTRICT"), nullable=False
    )
    employer: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_employer: Mapped[str] = mapped_column(Text, nullable=False)
    parent_group: Mapped[str] = mapped_column(Text, nullable=False, default="")
    corporate_cluster_id: Mapped[str] = mapped_column(
        ForeignKey("corporate_clusters.corporate_cluster_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    canonical_name_occurrences: Mapped[int | None] = mapped_column(Integer)
    duplicate_review_flag: Mapped[str] = mapped_column(Text, nullable=False, default="")
    entity_class: Mapped[str] = mapped_column(Text, nullable=False)
    career_scan_eligible: Mapped[str] = mapped_column(String(32), nullable=False)
    sector: Mapped[str] = mapped_column(Text, nullable=False)
    discovery_geography: Mapped[str] = mapped_column(Text, nullable=False)
    org_type: Mapped[str] = mapped_column(Text, nullable=False)
    corporate_website: Mapped[str] = mapped_column(Text, nullable=False, default="")
    website_status: Mapped[str] = mapped_column(Text, nullable=False, default="")
    careers_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    career_scan_status: Mapped[str] = mapped_column(Text, nullable=False)
    discovery_source: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    freeze_version: Mapped[str] = mapped_column(String(32), nullable=False)
    freeze_status: Mapped[str] = mapped_column(String(64), nullable=False)
    resolved_corporate_website: Mapped[str] = mapped_column(Text, nullable=False, default="")
    resolved_careers_landing_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    resolved_jobs_search_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    portal_scope: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ats_family: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ats_confidence: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    portal_resolution_status: Mapped[str] = mapped_column(String(64), nullable=False)
    portal_verification_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    portal_verified_date: Mapped[date | None] = mapped_column(Date)
    resolution_parent_override: Mapped[str] = mapped_column(Text, nullable=False, default="")
    resolution_wave: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    raw_row_json: Mapped[str] = mapped_column(Text, nullable=False)

    cluster: Mapped[CorporateCluster] = relationship(back_populates="records")


class Portal(Base):
    """Deduplicated operational endpoint, independent from company-specific metadata."""

    __tablename__ = "portals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    normalized_jobs_url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    jobs_search_url: Mapped[str] = mapped_column(Text, nullable=False)
    scheme: Mapped[str] = mapped_column(String(16), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    ats_families_json: Mapped[str] = mapped_column(Text, nullable=False)
    ats_confidences_json: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_conflict: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cluster_count: Mapped[int] = mapped_column(Integer, nullable=False)
    active_in_registry: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    scan_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    access_state: Mapped[str] = mapped_column(String(32), nullable=False, default="AVAILABLE")
    health_state: Mapped[str] = mapped_column(String(32), nullable=False, default="UNKNOWN")
    last_http_status: Mapped[int | None] = mapped_column(Integer)
    last_redirect_target: Mapped[str | None] = mapped_column(Text)
    last_successful_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_block_reason: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consecutive_empty_scans: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    import_batch_id: Mapped[int] = mapped_column(
        ForeignKey("import_batches.id", ondelete="RESTRICT"), nullable=False
    )

    cluster_mappings: Mapped[list[ClusterPortalMapping]] = relationship(back_populates="portal")
    source_jobs: Mapped[list[SourceJob]] = relationship(back_populates="portal")
    scan_attempts: Mapped[list[PortalScanAttempt]] = relationship(back_populates="portal")


class ClusterPortalMapping(Base):
    """Provenance-rich relation between a cluster and a shared portal."""

    __tablename__ = "cluster_portal_mappings"
    __table_args__ = (
        UniqueConstraint("corporate_cluster_id", "portal_id", name="uq_cluster_portal"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    corporate_cluster_id: Mapped[str] = mapped_column(
        ForeignKey("corporate_clusters.corporate_cluster_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    portal_id: Mapped[int] = mapped_column(
        ForeignKey("portals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resolved_corporate_website: Mapped[str] = mapped_column(Text, nullable=False)
    resolved_careers_landing_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_jobs_search_url: Mapped[str] = mapped_column(Text, nullable=False)
    portal_scope: Mapped[str] = mapped_column(Text, nullable=False)
    ats_family: Mapped[str] = mapped_column(Text, nullable=False)
    ats_confidence: Mapped[str] = mapped_column(String(64), nullable=False)
    portal_resolution_status: Mapped[str] = mapped_column(String(64), nullable=False)
    portal_verification_url: Mapped[str] = mapped_column(Text, nullable=False)
    portal_verified_date: Mapped[date] = mapped_column(Date, nullable=False)
    resolution_parent_override: Mapped[str] = mapped_column(Text, nullable=False, default="")
    resolution_wave: Mapped[str] = mapped_column(String(16), nullable=False)
    source_record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    import_batch_id: Mapped[int] = mapped_column(
        ForeignKey("import_batches.id", ondelete="RESTRICT"), nullable=False
    )

    cluster: Mapped[CorporateCluster] = relationship(back_populates="portal_mappings")
    portal: Mapped[Portal] = relationship(back_populates="cluster_mappings")


class RegistryChangeAudit(Base):
    """Immutable before/after evidence for a versioned registry change."""

    __tablename__ = "registry_change_audit"
    __table_args__ = (
        UniqueConstraint(
            "import_batch_id", "corporate_cluster_id", name="uq_registry_batch_cluster"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_batch_id: Mapped[int] = mapped_column(
        ForeignKey("import_batches.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    corporate_cluster_id: Mapped[str] = mapped_column(
        ForeignKey("corporate_clusters.corporate_cluster_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_url: Mapped[str] = mapped_column(Text, nullable=False)
    verified_date: Mapped[date] = mapped_column(Date, nullable=False)
    before_json: Mapped[str] = mapped_column(Text, nullable=False)
    after_json: Mapped[str] = mapped_column(Text, nullable=False)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class ScanRun(Base):
    __tablename__ = "scan_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    input_import_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_batches.id", ondelete="RESTRICT"), index=True
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="RUNNING")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    portal_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    http_2xx_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    http_3xx_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    http_4xx_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    http_5xx_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    http_429_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    jobs_discovered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_jobs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_jobs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    jobs_closed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_summary_json: Mapped[str | None] = mapped_column(Text)
    config_snapshot_json: Mapped[str | None] = mapped_column(Text)
    pipeline_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="NOT_PROCESSED"
    )

    portal_attempts: Mapped[list[PortalScanAttempt]] = relationship(back_populates="scan_run")
    source_jobs: Mapped[list[SourceJob]] = relationship(back_populates="scan_run")
    job_observations: Mapped[list[JobObservation]] = relationship(back_populates="scan_run")


class PortalScanAttempt(Base):
    __tablename__ = "portal_scan_attempts"
    __table_args__ = (UniqueConstraint("scan_run_id", "portal_id", name="uq_scan_run_portal"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_run_id: Mapped[int] = mapped_column(
        ForeignKey("scan_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    portal_id: Mapped[int] = mapped_column(
        ForeignKey("portals.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    adapter: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    http_status: Mapped[int | None] = mapped_column(Integer)
    retries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    jobs_observed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    snapshot_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    warnings_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    response_sha256: Mapped[str | None] = mapped_column(String(64))
    cache_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_type: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)

    scan_run: Mapped[ScanRun] = relationship(back_populates="portal_attempts")
    portal: Mapped[Portal] = relationship(back_populates="scan_attempts")


class CanonicalJob(Base):
    __tablename__ = "canonical_jobs"

    canonical_job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    corporate_cluster_id: Mapped[str | None] = mapped_column(
        ForeignKey("corporate_clusters.corporate_cluster_id", ondelete="SET NULL"), index=True
    )
    canonical_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    filter_status: Mapped[str] = mapped_column(String(32), nullable=False, default="REVIEW")
    primary_apply_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_title: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str] = mapped_column(Text, nullable=False, default="")
    country: Mapped[str | None] = mapped_column(String(128), index=True)
    city: Mapped[str | None] = mapped_column(String(255))
    workplace_type: Mapped[str | None] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    employment_type: Mapped[str | None] = mapped_column(String(128))
    seniority: Mapped[str | None] = mapped_column(String(64), index=True)
    cyber_category: Mapped[str | None] = mapped_column(String(128), index=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_successful_run_id: Mapped[int | None] = mapped_column(ForeignKey("scan_runs.id"))

    cluster: Mapped[CorporateCluster | None] = relationship(back_populates="canonical_jobs")
    source_jobs: Mapped[list[SourceJob]] = relationship(back_populates="canonical_job")


class SourceJob(Base):
    __tablename__ = "source_jobs"
    __table_args__ = (
        UniqueConstraint("source", "source_job_id", name="uq_source_job_identity"),
        Index("ix_source_jobs_apply_url", "apply_url"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_run_id: Mapped[int] = mapped_column(
        ForeignKey("scan_runs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    portal_id: Mapped[int | None] = mapped_column(
        ForeignKey("portals.id", ondelete="SET NULL"), index=True
    )
    canonical_job_id: Mapped[str | None] = mapped_column(
        ForeignKey("canonical_jobs.canonical_job_id", ondelete="SET NULL"), index=True
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    source_job_id: Mapped[str] = mapped_column(String(500), nullable=False)
    native_source_job_id: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    apply_url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_apply_url: Mapped[str] = mapped_column(Text, nullable=False)
    ats_job_id: Mapped[str | None] = mapped_column(String(500))
    requisition_id: Mapped[str | None] = mapped_column(String(500))
    raw_title: Mapped[str] = mapped_column(Text, nullable=False)
    raw_company: Mapped[str] = mapped_column(Text, nullable=False, default="")
    resolved_corporate_cluster_id: Mapped[str] = mapped_column(String(32), nullable=False, default="", index=True)
    resolved_company_name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    raw_location: Mapped[str] = mapped_column(Text, nullable=False, default="")
    raw_country: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    raw_city: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    raw_employment_type: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    raw_workplace_type: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    raw_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Optional second-stage detail-page enrichment. Listing/search payload remains preserved
    # in raw_* + raw_payload_json; these fields hold higher-fidelity official detail data.
    detail_title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    detail_location: Mapped[str] = mapped_column(Text, nullable=False, default="")
    detail_country: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    detail_city: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    detail_employment_type: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    detail_workplace_type: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    detail_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    detail_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    detail_payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    detail_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    adapter: Mapped[str] = mapped_column(String(128), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_payload_json: Mapped[str | None] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    missing_successful_scans: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ai_status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING_AI", index=True)
    ai_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ai_last_error: Mapped[str | None] = mapped_column(Text)
    ai_last_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    scan_run: Mapped[ScanRun] = relationship(back_populates="source_jobs")
    portal: Mapped[Portal | None] = relationship(back_populates="source_jobs")
    canonical_job: Mapped[CanonicalJob | None] = relationship(back_populates="source_jobs")
    observations: Mapped[list[JobObservation]] = relationship(back_populates="source_job")
    ai_analyses: Mapped[list[JobAiAnalysis]] = relationship(back_populates="source_job")


class JobAiAnalysis(Base):
    """Versioned structured AI interpretation of a discovered source job."""

    __tablename__ = "job_ai_analyses"
    __table_args__ = (
        UniqueConstraint(
            "source_job_row_id",
            "model",
            "prompt_version",
            "schema_version",
            "input_payload_sha256",
            name="uq_job_ai_analysis_input_version",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_job_row_id: Mapped[int] = mapped_column(
        ForeignKey("source_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    input_payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    is_cybersecurity: Mapped[bool | None] = mapped_column(Boolean)
    needs_more_detail: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    analysis_json: Mapped[str] = mapped_column(Text, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)

    source_job: Mapped[SourceJob] = relationship(back_populates="ai_analyses")


class JobObservation(Base):
    """Immutable per-run observation; unchanged payloads may omit duplicate raw JSON."""

    __tablename__ = "job_observations"
    __table_args__ = (
        UniqueConstraint("source_job_row_id", "scan_run_id", name="uq_job_observation_run"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_job_row_id: Mapped[int] = mapped_column(
        ForeignKey("source_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scan_run_id: Mapped[int] = mapped_column(
        ForeignKey("scan_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_changed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    raw_payload_json: Mapped[str | None] = mapped_column(Text)
    filter_status: Mapped[str] = mapped_column(String(32), nullable=False)
    filter_decision_json: Mapped[str] = mapped_column(Text, nullable=False)
    cluster_resolution_json: Mapped[str] = mapped_column(Text, nullable=False)

    source_job: Mapped[SourceJob] = relationship(back_populates="observations")
    scan_run: Mapped[ScanRun] = relationship(back_populates="job_observations")


def model_table_names() -> list[str]:
    """Return stable table names for diagnostics and tests."""

    return sorted(Base.metadata.tables)


JSONMapping = dict[str, Any]
