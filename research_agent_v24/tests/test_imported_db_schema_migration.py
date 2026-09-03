from sqlalchemy import create_engine, inspect

from research_agent.db.migrations import create_schema


def test_additive_migration_adds_detail_columns_to_legacy_source_jobs(tmp_path):
    database = tmp_path / "legacy_pilot.db"
    engine = create_engine(f"sqlite:///{database}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE source_jobs ("
            "id INTEGER PRIMARY KEY, "
            "raw_title TEXT NOT NULL DEFAULT ''"
            ")"
        )

    create_schema(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("source_jobs")}
    assert {
        "detail_title",
        "detail_location",
        "detail_country",
        "detail_city",
        "detail_employment_type",
        "detail_workplace_type",
        "detail_description",
        "detail_url",
        "detail_payload_sha256",
        "detail_fetched_at",
    } <= columns
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA integrity_check").scalar() == "ok"
