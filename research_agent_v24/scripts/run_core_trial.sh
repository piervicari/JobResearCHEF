#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RUNTIME_DB_PATH="${RESEARCH_AGENT_RUNTIME_DB_PATH:-$HOME/.local/share/research-agent/research_agent.db}"
RUNTIME_DB_URL="sqlite:///$RUNTIME_DB_PATH"

printf '%s\n' "RESEARCH AGENT — ONE-COMMAND CORE TRIAL" \
  "project_root: $ROOT_DIR" \
  "runtime_db: $RUNTIME_DB_PATH" \
  "dashboard: http://127.0.0.1:8501" \
  ""

echo "===== DEPENDENCIES ====="
uv sync --dev --extra dashboard

echo
echo "===== PERSISTENT SECRETS ====="
uv run research-agent bootstrap-secrets

echo
echo "===== PERSISTENT RUNTIME DB ====="
RESEARCH_AGENT_RUNTIME_DB_PATH="$RUNTIME_DB_PATH" ./scripts/bootstrap_runtime_db.sh

echo
echo "===== DASHBOARD ====="
RESEARCH_AGENT_DATABASE_URL="$RUNTIME_DB_URL" \
RESEARCH_AGENT_RUNTIME_DB_PATH="$RUNTIME_DB_PATH" \
  ./scripts/ensure_dashboard.sh

echo
echo "===== CORE EXPANSION ====="
P0_CORE_DB_URL="$RUNTIME_DB_URL" \
P0_CORE_SKIP_IMPORT=1 \
  ./scripts/run_p0_core_expansion.sh
