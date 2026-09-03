from research_agent.db.models import model_table_names


def test_minimum_data_model_tables_are_present() -> None:
    assert {
        "import_batches",
        "company_records",
        "corporate_clusters",
        "portals",
        "cluster_portal_mappings",
        "registry_change_audit",
        "scan_runs",
        "portal_scan_attempts",
        "source_jobs",
        "canonical_jobs",
        "job_observations",
    }.issubset(model_table_names())
