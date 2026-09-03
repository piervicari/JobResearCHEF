#!/usr/bin/env bash
set -u -o pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
DB_URL="${P0_PILOT_DB_URL:-sqlite:///data/pilot/research_agent_pilot.db}"
DETAIL_LIMIT="${P0_DETAIL_LIMIT:-5}"
DETAIL_MAX_PER_HOST="${P0_DETAIL_MAX_PER_HOST:-2}"
STAMP="$(date '+%Y%m%d-%H%M%S')"
REPORT_DIR="${TEST_REPORT_DIR:-output/test_runs}"
mkdir -p "$REPORT_DIR"
REPORT_FILE="$REPORT_DIR/p0_detail_followup_${STAMP}.log"
exec > >(tee -a "$REPORT_FILE") 2>&1

echo "RESEARCH AGENT P0 SELECTIVE DETAIL FOLLOW-UP"
echo "started_at: $(date -Iseconds)"
echo "database_url: $DB_URL"
echo "detail_limit: $DETAIL_LIMIT"
echo "detail_max_per_host: $DETAIL_MAX_PER_HOST"
echo "report_file: $REPORT_FILE"
echo
run_step() {
  local label="$1"; shift
  echo "===== $label ====="
  echo "+ $*"
  "$@"; local rc=$?
  echo "exit_code: $rc"; echo
  return $rc
}
run_step "PERSISTENT SECRETS" uv run research-agent bootstrap-secrets || exit 2
run_step "IMPORT LATEST PILOT DB" ./scripts/bootstrap_latest_pilot_db.sh || exit 3
run_step "CURRENT CYBER" uv run research-agent show-ai-results --database-url "$DB_URL" --status CYBER --limit 100 --full || exit 4
run_step "DETAIL DRY RUN" uv run research-agent enrich-details --database-url "$DB_URL" --limit "$DETAIL_LIMIT" --max-jobs-per-host "$DETAIL_MAX_PER_HOST" --dry-run || exit 5
run_step "DETAIL LIVE" uv run research-agent enrich-details --database-url "$DB_URL" --limit "$DETAIL_LIMIT" --max-jobs-per-host "$DETAIL_MAX_PER_HOST"
DETAIL_RC=$?
if [[ $DETAIL_RC -ne 0 ]]; then
  echo "ABORT: detail enrichment failed; AI re-analysis skipped."
  echo "REPORT READY: $REPORT_FILE"
  exit "$DETAIL_RC"
fi
run_step "AI REANALYSIS DRY RUN" uv run research-agent analyze-pending --database-url "$DB_URL" --limit "$DETAIL_LIMIT" --batch-size "$DETAIL_LIMIT" --dry-run || exit 6
run_step "AI REANALYSIS LIVE" uv run research-agent analyze-pending --database-url "$DB_URL" --limit "$DETAIL_LIMIT" --batch-size "$DETAIL_LIMIT"
AI_RC=$?
run_step "LATEST CYBER FULL" uv run research-agent show-ai-results --database-url "$DB_URL" --status CYBER --limit 100 --full
CYBER_RC=$?
run_step "LATEST NEEDS MORE DETAIL" uv run research-agent show-ai-results --database-url "$DB_URL" --status NEEDS_MORE_DETAIL --limit 100 --full
NEEDS_RC=$?
echo "finished_at: $(date -Iseconds)"
echo "detail_exit_code: $DETAIL_RC"
echo "ai_exit_code: $AI_RC"
echo "cyber_results_exit_code: $CYBER_RC"
echo "needs_results_exit_code: $NEEDS_RC"
echo "REPORT READY: $REPORT_FILE"
if [[ $AI_RC -ne 0 ]]; then exit "$AI_RC"; fi
if [[ $CYBER_RC -ne 0 ]]; then exit "$CYBER_RC"; fi
exit "$NEEDS_RC"
