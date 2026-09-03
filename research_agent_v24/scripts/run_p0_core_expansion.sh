#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

DB_URL="${P0_CORE_DB_URL:-sqlite:///data/pilot/research_agent_pilot.db}"
AI_LIMIT="${P0_CORE_AI_LIMIT:-120}"
BATCH_SIZE="${P0_CORE_BATCH_SIZE:-10}"
STAMP="$(date '+%Y%m%d-%H%M%S')"
REPORT_DIR="${TEST_REPORT_DIR:-output/test_runs}"
mkdir -p "$REPORT_DIR"
REPORT_FILE="$REPORT_DIR/p0_core_expansion_${STAMP}.log"

exec > >(tee -a "$REPORT_FILE") 2>&1

echo "RESEARCH AGENT P0 FIRST CORE EXPANSION"
echo "started_at: $(date -Iseconds)"
echo "database_url: $DB_URL"
echo "cohort_file: data/pilot/p0_core_expansion_cohort_v0_1.yaml"
echo "ai_limit: $AI_LIMIT"
echo "batch_size: $BATCH_SIZE"
echo "report_file: $REPORT_FILE"
echo

run_step() {
  local label="$1"
  shift
  echo "===== $label ====="
  echo "+ $*"
  "$@"
  local rc=$?
  echo "exit_code: $rc"
  echo
  return $rc
}

run_step "PERSISTENT SECRETS" uv run research-agent bootstrap-secrets || exit 2
if [[ "${P0_CORE_SKIP_IMPORT:-0}" == "1" ]]; then
  echo "===== RUNTIME DB ====="
  echo "database_url: $DB_URL"
  echo "bootstrap_import: skipped (persistent runtime DB already prepared)"
  echo
else
  run_step "IMPORT LATEST PILOT DB" ./scripts/bootstrap_latest_pilot_db.sh || exit 3
fi


run_step "STRIPE REGISTRY CORRECTION" uv run research-agent apply-runtime-registry-changes \
  data/portal_resolution/registry_corrections_v23_stripe_greenhouse.csv \
  --source-version v23-stripe-greenhouse --database-url "$DB_URL" || exit 5

STRIPE_PORTAL_ID="$(RESEARCH_AGENT_STRIPE_DB_URL="$DB_URL" uv run python - <<'PY2'
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
        raise SystemExit('Stripe portal missing after registry correction')
    print(row[0])
PY2
)"
echo "stripe_portal_id: $STRIPE_PORTAL_ID"
echo

# Offline hygiene for the two fully-described rows that were classified under the
# pre-v3 NEEDS_MORE_DETAIL contract. This deliberately does NOT requeue every old
# prompt-version row and therefore preserves free-provider quota.
run_step "SEMANTIC CLEANUP DRY RUN" uv run research-agent requeue-semantic-cleanup \
  --database-url "$DB_URL" --limit 100 --min-description-chars 1000 --dry-run || exit 4
run_step "SEMANTIC CLEANUP APPLY" uv run research-agent requeue-semantic-cleanup \
  --database-url "$DB_URL" --limit 100 --min-description-chars 1000 || exit 5

# Reuse the already-tested scan-pilot safety envelope. Two groups of five keep the
# per-command stop-on-block behavior while expanding to ten employers in one report.
run_step "CORE NETWORK BATCH A DRY RUN" uv run research-agent scan-pilot \
  --database-url "$DB_URL" \
  --portal-id 265 --portal-id 275 --portal-id 10 --portal-id 1 --portal-id 133 \
  --dry-run || exit 6
run_step "CORE NETWORK BATCH A LIVE" uv run research-agent scan-pilot \
  --database-url "$DB_URL" \
  --portal-id 265 --portal-id 275 --portal-id 10 --portal-id 1 --portal-id 133 || {
    echo "ABORT: batch A hit a network/access gate; batch B is intentionally skipped."
    echo "REPORT READY: $REPORT_FILE"
    exit 7
  }

run_step "CORE NETWORK BATCH B DRY RUN" uv run research-agent scan-pilot \
  --database-url "$DB_URL" \
  --portal-id "$STRIPE_PORTAL_ID" --portal-id 137 --portal-id 5 --portal-id 44 --portal-id 3 \
  --dry-run || exit 8
run_step "CORE NETWORK BATCH B LIVE" uv run research-agent scan-pilot \
  --database-url "$DB_URL" \
  --portal-id 276 --portal-id 137 --portal-id 5 --portal-id 44 --portal-id 3 || {
    echo "ABORT: batch B hit a network/access gate; AI processing is skipped for review."
    echo "REPORT READY: $REPORT_FILE"
    exit 9
  }

run_step "AI QUEUE DRY RUN" uv run research-agent analyze-pending \
  --database-url "$DB_URL" --limit "$AI_LIMIT" --batch-size "$BATCH_SIZE" --dry-run || exit 10

set +e
run_step "AI LIVE" uv run research-agent analyze-pending \
  --database-url "$DB_URL" --limit "$AI_LIMIT" --batch-size "$BATCH_SIZE"
AI_RC=$?
set -e

run_step "LATEST CYBER FULL" uv run research-agent show-ai-results \
  --database-url "$DB_URL" --status CYBER --limit 200 --full
CYBER_RC=$?
run_step "LATEST NEEDS MORE DETAIL FULL" uv run research-agent show-ai-results \
  --database-url "$DB_URL" --status NEEDS_MORE_DETAIL --limit 200 --full
NEEDS_RC=$?

echo "finished_at: $(date -Iseconds)"
echo "ai_exit_code: $AI_RC"
echo "cyber_results_exit_code: $CYBER_RC"
echo "needs_results_exit_code: $NEEDS_RC"
echo "REPORT READY: $REPORT_FILE"

if [[ $AI_RC -ne 0 ]]; then exit "$AI_RC"; fi
if [[ $CYBER_RC -ne 0 ]]; then exit "$CYBER_RC"; fi
exit "$NEEDS_RC"
