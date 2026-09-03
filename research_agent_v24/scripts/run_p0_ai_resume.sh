#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

mkdir -p output/test_runs
STAMP="$(date +%Y%m%d-%H%M%S)"
REPORT="output/test_runs/p0_ai_resume_${STAMP}.log"
DB_URL="sqlite:///data/pilot/research_agent_pilot.db"
LIMIT="${P0_AI_RESUME_LIMIT:-10}"
BATCH_SIZE="${P0_AI_RESUME_BATCH_SIZE:-5}"

exec > >(tee -a "$REPORT") 2>&1

echo "RESEARCH AGENT P0 AI RESUME — NO CAREER-SITE REQUESTS"
echo "started_at: $(date -Iseconds)"
echo "database_url: $DB_URL"
echo "limit: $LIMIT"
echo "batch_size: $BATCH_SIZE"
echo "report_file: $REPORT"

echo
echo "===== PERSISTENT SECRETS ====="
uv run research-agent bootstrap-secrets

echo
echo "===== IMPORT LATEST PILOT DB ====="
./scripts/bootstrap_latest_pilot_db.sh

echo
echo "===== PENDING AI DRY RUN ====="
uv run research-agent analyze-pending \
  --database-url "$DB_URL" \
  --limit "$LIMIT" \
  --batch-size "$BATCH_SIZE" \
  --dry-run

echo
echo "===== PENDING AI LIVE ====="
set +e
uv run research-agent analyze-pending \
  --database-url "$DB_URL" \
  --limit "$LIMIT" \
  --batch-size "$BATCH_SIZE"
AI_EXIT=$?
set -e

echo
echo "===== LATEST CYBER FULL ====="
uv run research-agent show-ai-results --database-url "$DB_URL" --status CYBER --limit 100 --full

echo
echo "===== LATEST NON-CYBER FULL ====="
uv run research-agent show-ai-results --database-url "$DB_URL" --status NON_CYBER --limit 100 --full

echo
echo "===== LATEST NEEDS MORE DETAIL ====="
uv run research-agent show-ai-results --database-url "$DB_URL" --status NEEDS_MORE_DETAIL --limit 100 --full

echo
echo "finished_at: $(date -Iseconds)"
echo "ai_exit_code: $AI_EXIT"
echo "REPORT READY: $REPORT"
exit "$AI_EXIT"
