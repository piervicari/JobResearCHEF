#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

DASHBOARD_HOST="${RESEARCH_AGENT_DASHBOARD_HOST:-127.0.0.1}"
DASHBOARD_PORT="${RESEARCH_AGENT_DASHBOARD_PORT:-8501}"
DASHBOARD_URL="http://${DASHBOARD_HOST}:${DASHBOARD_PORT}"
DB_PATH="${RESEARCH_AGENT_RUNTIME_DB_PATH:-$HOME/.local/share/research-agent/research_agent.db}"
DB_URL="${RESEARCH_AGENT_DATABASE_URL:-sqlite:///$DB_PATH}"
STATE_DIR="${RESEARCH_AGENT_DASHBOARD_STATE_DIR:-$HOME/.local/state/research-agent}"
LOG_DIR="${RESEARCH_AGENT_DASHBOARD_LOG_DIR:-$HOME/.local/state/research-agent}"
PID_FILE="$STATE_DIR/dashboard.pid"
META_FILE="$STATE_DIR/dashboard.env"
LOG_FILE="$LOG_DIR/dashboard.log"
mkdir -p "$STATE_DIR" "$LOG_DIR"

health_ok() {
  curl --silent --show-error --fail --max-time 2 \
    "$DASHBOARD_URL/_stcore/health" >/dev/null 2>&1
}

if health_ok; then
  if [[ -f "$META_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$META_FILE" || true
    if [[ "${DASHBOARD_DATABASE_URL:-}" == "$DB_URL" ]]; then
      echo "dashboard_status: already_running"
      echo "dashboard_url: $DASHBOARD_URL"
      echo "dashboard_database_url: $DB_URL"
      exit 0
    fi

    # A dashboard previously managed by us is healthy but points to an obsolete
    # version-local DB. Restart it once on the persistent runtime DB.
    old_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    echo "dashboard_status: restarting_managed_dashboard_for_runtime_db"
    echo "old_dashboard_database_url: ${DASHBOARD_DATABASE_URL:-unknown}"
    echo "requested_database_url: $DB_URL"
    if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
      kill "$old_pid" 2>/dev/null || true
      for _ in $(seq 1 10); do
        if ! health_ok; then break; fi
        sleep 1
      done
    fi
  else
    echo "dashboard_status: already_running_unmanaged"
    echo "dashboard_url: $DASHBOARD_URL"
    echo "dashboard_error: port is occupied by a healthy Streamlit dashboard not managed by this project"
    echo "dashboard_action: stop that dashboard once, then rerun this script"
    exit 2
  fi
fi

# Remove stale pid metadata only when health is down.
if [[ -f "$PID_FILE" ]]; then
  old_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
    kill "$old_pid" 2>/dev/null || true
  fi
  rm -f "$PID_FILE"
fi

cat > "$META_FILE" <<META
DASHBOARD_DATABASE_URL='$DB_URL'
DASHBOARD_PROJECT_ROOT='$ROOT_DIR'
DASHBOARD_URL='$DASHBOARD_URL'
META

nohup env RESEARCH_AGENT_DATABASE_URL="$DB_URL" \
  uv run --extra dashboard streamlit run src/research_agent/dashboard/app.py \
  --server.address "$DASHBOARD_HOST" \
  --server.port "$DASHBOARD_PORT" \
  --server.headless true \
  --browser.gatherUsageStats false \
  >"$LOG_FILE" 2>&1 &
pid=$!
echo "$pid" > "$PID_FILE"

for _ in $(seq 1 30); do
  if health_ok; then
    echo "dashboard_status: started"
    echo "dashboard_pid: $pid"
    echo "dashboard_url: $DASHBOARD_URL"
    echo "dashboard_database_url: $DB_URL"
    echo "dashboard_log: $LOG_FILE"
    if command -v open >/dev/null 2>&1; then
      open "$DASHBOARD_URL" >/dev/null 2>&1 || true
    fi
    exit 0
  fi
  sleep 1
done

echo "dashboard_status: failed_to_start"
echo "dashboard_log: $LOG_FILE"
tail -80 "$LOG_FILE" 2>/dev/null || true
exit 1
