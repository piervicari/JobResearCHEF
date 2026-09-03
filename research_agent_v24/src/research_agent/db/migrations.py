"""Small additive MVP schema bootstrap; versioned migrations can replace this later."""

from sqlalchemy import Engine, inspect

from research_agent.db.models import Base


def create_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    _apply_additive_sqlite_migrations(engine)


def _apply_additive_sqlite_migrations(engine: Engine) -> None:
    """Keep early local databases usable while the MVP schema is still additive-only."""

    expected = {
        "source_jobs": {
            "first_seen_at": "DATETIME",
            "last_seen_at": "DATETIME",
            "is_active": "BOOLEAN NOT NULL DEFAULT 1",
            "closed_at": "DATETIME",
            "missing_successful_scans": "INTEGER NOT NULL DEFAULT 0",
            "raw_country": "VARCHAR(128) NOT NULL DEFAULT ''",
            "raw_city": "VARCHAR(255) NOT NULL DEFAULT ''",
            "raw_employment_type": "VARCHAR(128) NOT NULL DEFAULT ''",
            "raw_workplace_type": "VARCHAR(32) NOT NULL DEFAULT ''",
            "native_source_job_id": "VARCHAR(500) NOT NULL DEFAULT ''",
            "resolved_corporate_cluster_id": "VARCHAR(32) NOT NULL DEFAULT ''",
            "resolved_company_name": "TEXT NOT NULL DEFAULT ''",
            "ai_status": "VARCHAR(32) NOT NULL DEFAULT 'PENDING_AI'",
            "ai_attempts": "INTEGER NOT NULL DEFAULT 0",
            "ai_last_error": "TEXT",
            "ai_last_analyzed_at": "DATETIME",
            "detail_title": "TEXT NOT NULL DEFAULT ''",
            "detail_location": "TEXT NOT NULL DEFAULT ''",
            "detail_country": "VARCHAR(128) NOT NULL DEFAULT ''",
            "detail_city": "VARCHAR(255) NOT NULL DEFAULT ''",
            "detail_employment_type": "VARCHAR(128) NOT NULL DEFAULT ''",
            "detail_workplace_type": "VARCHAR(32) NOT NULL DEFAULT ''",
            "detail_description": "TEXT NOT NULL DEFAULT ''",
            "detail_url": "TEXT NOT NULL DEFAULT ''",
            "detail_payload_sha256": "VARCHAR(64) NOT NULL DEFAULT ''",
            "detail_fetched_at": "DATETIME",
        },
        "canonical_jobs": {
            "filter_status": "VARCHAR(32) NOT NULL DEFAULT 'REVIEW'",
            "primary_apply_url": "TEXT NOT NULL DEFAULT ''",
        },
        "portals": {
            "consecutive_empty_scans": "INTEGER NOT NULL DEFAULT 0",
            "cooldown_until": "DATETIME",
            "last_block_reason": "TEXT",
            "scan_enabled": "BOOLEAN NOT NULL DEFAULT 1",
            "access_state": "VARCHAR(32) NOT NULL DEFAULT 'AVAILABLE'",
        },
        "scan_runs": {
            "pipeline_status": "VARCHAR(32) NOT NULL DEFAULT 'NOT_PROCESSED'",
            "input_import_batch_id": "INTEGER REFERENCES import_batches(id)",
        },
        "portal_scan_attempts": {
            "snapshot_complete": "BOOLEAN NOT NULL DEFAULT 0",
            "warnings_json": "TEXT NOT NULL DEFAULT '[]'",
        },
    }
    inspector = inspect(engine)
    missing: list[tuple[str, str, str]] = []
    for table, columns in expected.items():
        if not inspector.has_table(table):
            continue
        present = {column["name"] for column in inspector.get_columns(table)}
        missing.extend(
            (table, column, definition)
            for column, definition in columns.items()
            if column not in present
        )
    if not missing:
        return
    if engine.dialect.name != "sqlite":
        raise RuntimeError("Schema upgrade required; automatic MVP migration is SQLite-only")
    with engine.begin() as connection:
        for table, column, definition in missing:
            connection.exec_driver_sql(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {definition}')
