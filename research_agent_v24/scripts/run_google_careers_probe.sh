#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RUNTIME_DB_PATH="${RESEARCH_AGENT_RUNTIME_DB_PATH:-$HOME/.local/share/research-agent/research_agent.db}"
DB_URL="sqlite:///$RUNTIME_DB_PATH"
STAMP="$(date +%Y%m%d-%H%M%S)"
REPORT_DIR="output/test_runs"
REPORT_FILE="$REPORT_DIR/google_careers_probe_${STAMP}.log"
mkdir -p "$REPORT_DIR"

exec > >(tee "$REPORT_FILE") 2>&1

printf '%s\n' \
  "RESEARCH AGENT V24 — GOOGLE CAREERS RPC + CYBER SCOPE PROBE" \
  "started_at: $(date -Iseconds)" \
  "database_url: $DB_URL" \
  "triage_batch_size: 100" \
  "google_network: concurrency=1 interval=1.25s pages<=200 requests<=220 retries=1" \
  "report_file: $REPORT_FILE" \
  ""

echo "===== DEPENDENCIES ====="
uv sync --dev --extra dashboard

echo
echo "===== PERSISTENT SECRETS ====="
uv run research-agent bootstrap-secrets

echo
echo "===== RUNTIME DB ====="
RESEARCH_AGENT_RUNTIME_DB_PATH="$RUNTIME_DB_PATH" ./scripts/bootstrap_runtime_db.sh

echo
echo "===== DASHBOARD ====="
RESEARCH_AGENT_DATABASE_URL="$DB_URL" RESEARCH_AGENT_RUNTIME_DB_PATH="$RUNTIME_DB_PATH" \
  ./scripts/ensure_dashboard.sh

GOOGLE_PORTAL_ID="$(RESEARCH_AGENT_GOOGLE_DB_URL="$DB_URL" uv run python - <<'PY'
import os
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from research_agent.db.models import ClusterPortalMapping, Portal

engine = create_engine(os.environ['RESEARCH_AGENT_GOOGLE_DB_URL'])
with Session(engine) as session:
    row = session.execute(
        select(Portal.id)
        .join(ClusterPortalMapping, ClusterPortalMapping.portal_id == Portal.id)
        .where(
            ClusterPortalMapping.corporate_cluster_id == 'CG-C65DC3B9A9',
            Portal.active_in_registry.is_(True),
            Portal.scan_enabled.is_(True),
        )
        .order_by(Portal.id.desc())
    ).first()
    if row is None:
        raise SystemExit('Google/Alphabet active portal not found')
    print(row[0])
PY
)"

echo "google_portal_id: $GOOGLE_PORTAL_ID"

echo
echo "===== GOOGLE ADAPTER PREFLIGHT — ZERO NETWORK ====="
RESEARCH_AGENT_GOOGLE_DB_URL="$DB_URL" RESEARCH_AGENT_GOOGLE_PORTAL_ID="$GOOGLE_PORTAL_ID" uv run python - <<'PY'
import os
from sqlalchemy import create_engine
from research_agent.pipeline.scanner import load_portal_targets
from research_agent.sources.ats.registry import default_adapter_registry

engine = create_engine(os.environ['RESEARCH_AGENT_GOOGLE_DB_URL'])
portal_id = int(os.environ['RESEARCH_AGENT_GOOGLE_PORTAL_ID'])
targets = load_portal_targets(engine, portal_ids={portal_id})
if len(targets) != 1:
    raise SystemExit(f'Expected one Google target, got {len(targets)}')
target = targets[0]
adapter = default_adapter_registry().select(target)
print(f'host: {target.host}')
print(f'jobs_search_url: {target.jobs_search_url}')
print(f'ats_families: {target.ats_families}')
print(f'selected_adapter: {getattr(adapter, "name", None)}')
if adapter is None or adapter.name != 'google_careers_rpc':
    raise SystemExit('Google target did not resolve to google_careers_rpc')
PY

echo
echo "===== GOOGLE STRUCTURED CATALOG SCAN ====="
RESEARCH_AGENT_SCANNER__GLOBAL_CONCURRENCY=1 \
RESEARCH_AGENT_SCANNER__PER_DOMAIN_CONCURRENCY=1 \
RESEARCH_AGENT_SCANNER__PER_DOMAIN_MIN_INTERVAL_SECONDS=1.25 \
RESEARCH_AGENT_SCANNER__MAX_RETRIES=1 \
RESEARCH_AGENT_SCANNER__JITTER_SECONDS=0.15 \
RESEARCH_AGENT_SCANNER__MAX_REQUESTS_PER_HOST_PER_RUN=220 \
RESEARCH_AGENT_SCANNER__MAX_REQUESTS_PER_RUN=220 \
RESEARCH_AGENT_SCANNER__MAX_PAGES_PER_PORTAL=200 \
RESEARCH_AGENT_SCANNER__BULK_CATALOG_MAX_JOBS_PER_PORTAL=5000 \
RESEARCH_AGENT_SCANNER__RUN_TIMEOUT_SECONDS=1800 \
uv run research-agent scan-discover \
  --database-url "$DB_URL" \
  --portal-id "$GOOGLE_PORTAL_ID"

echo
echo "===== GOOGLE RAW CATALOG SUMMARY ====="
RESEARCH_AGENT_GOOGLE_DB_URL="$DB_URL" RESEARCH_AGENT_GOOGLE_PORTAL_ID="$GOOGLE_PORTAL_ID" uv run python - <<'PY'
import os
from collections import Counter
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from research_agent.db.models import SourceJob

engine = create_engine(os.environ['RESEARCH_AGENT_GOOGLE_DB_URL'])
portal_id = int(os.environ['RESEARCH_AGENT_GOOGLE_PORTAL_ID'])
with Session(engine) as session:
    rows = session.scalars(
        select(SourceJob)
        .where(SourceJob.portal_id == portal_id, SourceJob.is_active.is_(True))
        .order_by(SourceJob.id)
    ).all()
ids = [row.native_source_job_id or row.source_job_id for row in rows]
print(f'active_rows: {len(rows)}')
print(f'unique_native_ids: {len(set(ids))}')
print(f'duplicate_native_ids: {len(ids) - len(set(ids))}')
print(f'descriptions_nonempty: {sum(bool((row.raw_description or "").strip()) for row in rows)}')
print(f'ai_status_counts_before_triage: {dict(sorted(Counter(row.ai_status for row in rows).items()))}')
PY

echo
echo "===== GOOGLE TRIAGE DRY RUN ====="
uv run research-agent triage-pending \
  --database-url "$DB_URL" \
  --portal-id "$GOOGLE_PORTAL_ID" \
  --limit 5000 \
  --batch-size 100 \
  --dry-run

echo
echo "===== GOOGLE TRIAGE LIVE ====="
uv run research-agent triage-pending \
  --database-url "$DB_URL" \
  --portal-id "$GOOGLE_PORTAL_ID" \
  --limit 5000 \
  --batch-size 100

echo
echo "===== GOOGLE FULL ANALYSIS DRY RUN ====="
uv run research-agent analyze-pending \
  --database-url "$DB_URL" \
  --portal-id "$GOOGLE_PORTAL_ID" \
  --limit 5000 \
  --batch-size 10 \
  --dry-run

echo
echo "===== GOOGLE FULL ANALYSIS LIVE ====="
uv run research-agent analyze-pending \
  --database-url "$DB_URL" \
  --portal-id "$GOOGLE_PORTAL_ID" \
  --limit 5000 \
  --batch-size 10

echo
echo "===== GOOGLE FINAL SUMMARY + CYBER JOBS ====="
RESEARCH_AGENT_GOOGLE_DB_URL="$DB_URL" RESEARCH_AGENT_GOOGLE_PORTAL_ID="$GOOGLE_PORTAL_ID" uv run python - <<'PY'
import os
from collections import Counter
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from research_agent.db.models import SourceJob

engine = create_engine(os.environ['RESEARCH_AGENT_GOOGLE_DB_URL'])
portal_id = int(os.environ['RESEARCH_AGENT_GOOGLE_PORTAL_ID'])
with Session(engine) as session:
    rows = session.scalars(
        select(SourceJob)
        .where(SourceJob.portal_id == portal_id, SourceJob.is_active.is_(True))
        .order_by(SourceJob.id)
    ).all()
counts = Counter(row.ai_status for row in rows)
print(f'active_rows: {len(rows)}')
print(f'final_status_counts: {dict(sorted(counts.items()))}')
print(f'pending_after_analysis: {counts.get("PENDING_AI", 0)}')
print('CYBER JOBS:')
for row in rows:
    if row.ai_status == 'CYBER':
        print(
            f'job_id={row.id} source_job_id={row.native_source_job_id or row.source_job_id} '
            f'title={row.raw_title!r} location={row.raw_location!r} source_url={row.source_url}'
        )
PY

echo
echo "finished_at: $(date -Iseconds)"
echo "REPORT READY: $REPORT_FILE"
