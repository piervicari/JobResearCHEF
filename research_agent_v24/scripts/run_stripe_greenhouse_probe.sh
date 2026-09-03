#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RUNTIME_DB_PATH="${RESEARCH_AGENT_RUNTIME_DB_PATH:-$HOME/.local/share/research-agent/research_agent.db}"
DB_URL="sqlite:///$RUNTIME_DB_PATH"
STAMP="$(date +%Y%m%d-%H%M%S)"
REPORT_DIR="output/test_runs"
REPORT_FILE="$REPORT_DIR/stripe_greenhouse_probe_${STAMP}.log"
mkdir -p "$REPORT_DIR"

exec > >(tee "$REPORT_FILE") 2>&1

printf '%s\n' \
  "RESEARCH AGENT — STRIPE GREENHOUSE + LARGE-BATCH TRIAGE PROBE" \
  "started_at: $(date -Iseconds)" \
  "database_url: $DB_URL" \
  "triage_batch_size: 100" \
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

echo
echo "===== STRIPE REGISTRY CORRECTION ====="
uv run research-agent apply-runtime-registry-changes \
  data/portal_resolution/registry_corrections_v23_stripe_greenhouse.csv \
  --source-version v23-stripe-greenhouse \
  --database-url "$DB_URL"

STRIPE_PORTAL_ID="$(RESEARCH_AGENT_STRIPE_DB_URL="$DB_URL" uv run python - <<'PY'
import os
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from research_agent.db.models import ClusterPortalMapping, Portal

engine = create_engine(os.environ['RESEARCH_AGENT_STRIPE_DB_URL'])
with Session(engine) as session:
    row = session.execute(
        select(Portal.id)
        .join(ClusterPortalMapping, ClusterPortalMapping.portal_id == Portal.id)
        .where(
            ClusterPortalMapping.corporate_cluster_id == 'CG-2FCB5A43A4',
            Portal.active_in_registry.is_(True),
            Portal.scan_enabled.is_(True),
        )
        .order_by(Portal.id.desc())
    ).first()
    if row is None:
        raise SystemExit('Stripe active portal not found after registry correction')
    print(row[0])
PY
)"

echo "stripe_portal_id: $STRIPE_PORTAL_ID"

echo
echo "===== STRIPE SCAN DRY RUN ====="
uv run research-agent scan-pilot \
  --database-url "$DB_URL" \
  --portal-id "$STRIPE_PORTAL_ID" \
  --dry-run

echo
echo "===== STRIPE SCAN LIVE ====="
uv run research-agent scan-pilot \
  --database-url "$DB_URL" \
  --portal-id "$STRIPE_PORTAL_ID"

echo
echo "===== STRIPE RAW CATALOG ====="
uv run research-agent show-portal-jobs \
  --database-url "$DB_URL" \
  --portal-id "$STRIPE_PORTAL_ID" \
  --limit 2000

echo
echo "===== STRIPE TRIAGE DRY RUN ====="
uv run research-agent triage-pending \
  --database-url "$DB_URL" \
  --portal-id "$STRIPE_PORTAL_ID" \
  --limit 2000 \
  --batch-size 100 \
  --dry-run

echo
echo "===== STRIPE TRIAGE LIVE ====="
uv run research-agent triage-pending \
  --database-url "$DB_URL" \
  --portal-id "$STRIPE_PORTAL_ID" \
  --limit 2000 \
  --batch-size 100

echo
echo "===== STRIPE FULL ANALYSIS DRY RUN ====="
uv run research-agent analyze-pending \
  --database-url "$DB_URL" \
  --portal-id "$STRIPE_PORTAL_ID" \
  --limit 1000 \
  --batch-size 10 \
  --dry-run

echo
echo "===== STRIPE FULL ANALYSIS LIVE ====="
uv run research-agent analyze-pending \
  --database-url "$DB_URL" \
  --portal-id "$STRIPE_PORTAL_ID" \
  --limit 1000 \
  --batch-size 10

echo
echo "===== STRIPE FINAL JOBS ====="
uv run research-agent show-portal-jobs \
  --database-url "$DB_URL" \
  --portal-id "$STRIPE_PORTAL_ID" \
  --limit 2000

echo
echo "===== CURRENT CYBER FULL ====="
uv run research-agent show-ai-results \
  --database-url "$DB_URL" \
  --status CYBER \
  --limit 200 \
  --full

echo
echo "finished_at: $(date -Iseconds)"
echo "REPORT READY: $REPORT_FILE"
