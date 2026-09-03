#!/usr/bin/env bash
set -euo pipefail

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
audit_dir=$(mktemp -d "${TMPDIR:-/tmp}/research-agent-final-audit.XXXXXX")
trap 'rm -rf -- "$audit_dir"' EXIT
audit_db="$audit_dir/final-audit.db"
database_url="sqlite:///$audit_db"

cd "$project_root"
uv run ruff check .
uv run pytest -q

uv run research-agent import-master \
  data/company_universe/master_company_universe_v1_5_portal_resolution_wave5.csv \
  --database-url "$database_url"

uv run research-agent apply-registry-changes \
  data/portal_resolution/registry_corrections_run17_v1.csv \
  --source-version registry-corrections-run17-v1 \
  --master-output "$audit_dir/v1_6.csv" \
  --database-url "$database_url"
uv run research-agent apply-registry-changes \
  data/portal_resolution/registry_corrections_run23_v1.csv \
  --source-version v1.7-registry-corrections-run23 \
  --master-output "$audit_dir/v1_7.csv" \
  --database-url "$database_url"
uv run research-agent apply-registry-changes \
  data/portal_resolution/registry_corrections_run24_v1.csv \
  --source-version v1.8-registry-corrections-run24 \
  --master-output "$audit_dir/v1_8.csv" \
  --database-url "$database_url"
uv run research-agent apply-registry-changes \
  data/portal_resolution/registry_corrections_run26_v1.csv \
  --source-version registry-corrections-run26-v1 \
  --master-output "$audit_dir/v1_9.csv" \
  --database-url "$database_url"
uv run research-agent apply-registry-changes \
  data/portal_resolution/registry_wave6_v1.csv \
  --source-version v1.10-wave6 \
  --master-output "$audit_dir/v1_10.csv" \
  --database-url "$database_url"
uv run research-agent import-company-aliases \
  data/company_aliases/company_aliases_v1.csv \
  --source-version company-aliases-v1 \
  --database-url "$database_url"

uv run research-agent validate-master \
  --database-url "$database_url" \
  --report "$audit_dir/master-validation.md" \
  --json-report "$audit_dir/master-validation.json"
uv run research-agent benchmark-taxonomy \
  --report "$audit_dir/taxonomy-benchmark.md" \
  --json-report "$audit_dir/taxonomy-benchmark.json"

uv run research-agent backup-db \
  --database-url "$database_url" \
  --output "$audit_dir/final-audit-backup.db"
uv run research-agent verify-recovery "$audit_dir/final-audit-backup.db" \
  --destination "$audit_dir/final-audit-restored.db" \
  --report "$audit_dir/recovery.md"

AUDIT_DATABASE_URL="$database_url" uv run python - <<'PY'
import os

from research_agent.dashboard.queries import (
    coverage_summary,
    discovery_coverage_rows,
    job_summary,
    sector_coverage_rows,
)
from research_agent.db.session import create_db_engine

engine = create_db_engine(os.environ["AUDIT_DATABASE_URL"])
coverage = coverage_summary(engine)
jobs = job_summary(engine)
assert coverage.master_rows == 12_503
assert coverage.corporate_clusters == 11_798
assert coverage.resolved_clusters == 589
assert coverage.unique_portals == 524
assert coverage.scanned_portals == 0
assert coverage.scannable_portals == 492
assert coverage.stale_portals == 0
assert jobs.total_canonical_jobs == 0
assert sum(int(row["master_rows"]) for row in discovery_coverage_rows(engine)) == 12_503
assert sum(int(row["master_rows"]) for row in sector_coverage_rows(engine)) == 12_503
print(f"dashboard_master_rows: {coverage.master_rows}")
print(f"dashboard_resolved_clusters: {coverage.resolved_clusters}")
print(f"dashboard_active_portals: {coverage.unique_portals}")
print(f"dashboard_scannable_portals: {coverage.scannable_portals}")
print("dashboard_geography_and_sector_coverage: PASS")
print("final_audit: PASS")
PY
