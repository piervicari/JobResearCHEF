#!/usr/bin/env bash
set -u -o pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

DB_URL="${P0_PILOT_DB_URL:-sqlite:///data/pilot/research_agent_pilot.db}"
AI_LIMIT="${P0_PILOT_AI_LIMIT:-50}"
BATCH_SIZE="${P0_PILOT_BATCH_SIZE:-10}"
STAMP="$(date '+%Y%m%d-%H%M%S')"
REPORT_DIR="${TEST_REPORT_DIR:-output/test_runs}"
mkdir -p "$REPORT_DIR"
REPORT_FILE="$REPORT_DIR/p0_end_to_end_pilot_${STAMP}.log"

exec > >(tee -a "$REPORT_FILE") 2>&1

echo "RESEARCH AGENT P0 END-TO-END PILOT"
echo "started_at: $(date -Iseconds)"
echo "project_root: $ROOT_DIR"
echo "database_url: $DB_URL"
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

run_step "PERSISTENT SECRETS" uv run research-agent bootstrap-secrets || {
  echo "ABORT: no reusable API-key env was found."
  echo "Create ~/.config/research-agent/.env once; do not put secrets in this report."
  exit 2
}

run_step "LLM PREFLIGHT" uv run research-agent llm-preflight || exit 3
run_step "RESET CLEAN PILOT DB" uv run research-agent prepare-pilot-db --replace || exit 4
run_step "NETWORK PILOT DRY RUN" uv run research-agent scan-pilot --database-url "$DB_URL" --dry-run || exit 5

run_step "NETWORK PILOT LIVE" uv run research-agent scan-pilot --database-url "$DB_URL"
SCAN_RC=$?
if [[ $SCAN_RC -ne 0 ]]; then
  echo "ABORT: network pilot stopped/failed; AI processing is intentionally skipped."
  echo "REPORT READY: $REPORT_FILE"
  exit "$SCAN_RC"
fi

run_step "AI PILOT DRY RUN" uv run research-agent analyze-pending \
  --database-url "$DB_URL" \
  --limit "$AI_LIMIT" \
  --batch-size "$BATCH_SIZE" \
  --dry-run || exit 6

run_step "AI PILOT LIVE" uv run research-agent analyze-pending \
  --database-url "$DB_URL" \
  --limit "$AI_LIMIT" \
  --batch-size "$BATCH_SIZE"
AI_RC=$?

run_step "CYBER RESULTS" uv run research-agent show-ai-results \
  --database-url "$DB_URL" \
  --status CYBER \
  --limit 100 \
  --full
CYBER_RC=$?

run_step "LATEST ALL AI RESULTS" uv run research-agent show-ai-results \
  --database-url "$DB_URL" \
  --limit 100
ALL_RC=$?

echo "finished_at: $(date -Iseconds)"
echo "scan_exit_code: $SCAN_RC"
echo "ai_exit_code: $AI_RC"
echo "cyber_results_exit_code: $CYBER_RC"
echo "all_results_exit_code: $ALL_RC"
echo "REPORT READY: $REPORT_FILE"

if [[ $AI_RC -ne 0 ]]; then exit "$AI_RC"; fi
if [[ $CYBER_RC -ne 0 ]]; then exit "$CYBER_RC"; fi
exit "$ALL_RC"
