#!/usr/bin/env bash
set -u -o pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

LIMIT="${AI_CANARY_LIMIT:-5}"
BATCH_SIZE="${AI_CANARY_BATCH_SIZE:-5}"
DB_URL="${AI_CANARY_DB_URL:-sqlite:///data/canary/research_agent_canary.db}"
STAMP="$(date '+%Y%m%d-%H%M%S')"
REPORT_DIR="${TEST_REPORT_DIR:-output/test_runs}"
mkdir -p "$REPORT_DIR"
REPORT_FILE="$REPORT_DIR/ai_micro_canary_${STAMP}.log"

# Mirror stdout+stderr to terminal and a shareable report file. No secret values are printed.
exec > >(tee -a "$REPORT_FILE") 2>&1

echo "RESEARCH AGENT AI MICRO-CANARY"
echo "started_at: $(date -Iseconds)"
echo "project_root: $ROOT_DIR"
echo "database_url: $DB_URL"
echo "limit: $LIMIT"
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

run_step "LLM PREFLIGHT" uv run research-agent llm-preflight || {
  echo "ABORT: preflight failed"
  echo "finished_at: $(date -Iseconds)"
  exit 2
}

run_step "RESET CANARY DB" uv run research-agent prepare-canary-db --replace || {
  echo "ABORT: canary DB preparation failed"
  echo "finished_at: $(date -Iseconds)"
  exit 3
}

run_step "AI DRY RUN" uv run research-agent analyze-pending \
  --database-url "$DB_URL" \
  --limit "$LIMIT" \
  --batch-size "$BATCH_SIZE" \
  --dry-run || {
  echo "ABORT: dry-run failed"
  echo "finished_at: $(date -Iseconds)"
  exit 4
}

run_step "AI LIVE RUN" uv run research-agent analyze-pending \
  --database-url "$DB_URL" \
  --limit "$LIMIT" \
  --batch-size "$BATCH_SIZE"
LIVE_RC=$?

# Always inspect whatever was persisted, even if the live run failed part-way.
run_step "AI RESULTS" uv run research-agent show-ai-results \
  --database-url "$DB_URL" \
  --limit "$LIMIT" \
  --full
RESULT_RC=$?

echo "finished_at: $(date -Iseconds)"
echo "live_exit_code: $LIVE_RC"
echo "results_exit_code: $RESULT_RC"
echo "REPORT READY: $REPORT_FILE"

if [[ $LIVE_RC -ne 0 ]]; then
  exit "$LIVE_RC"
fi
exit "$RESULT_RC"
