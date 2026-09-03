#!/usr/bin/env bash
# One-command operator entry point for the Tier-S Operational Source Control Plane.
#
# Steps:
#   1. validate the structured operational source registry CSV;
#   2. reconcile employers against the existing CorporateCluster table;
#   3. emit unmatched employers and resolution queues / summary (dry run);
#   4. sync if validation passes (idempotent, additive, offline);
#   5. re-emit reports and a timestamped log under output/test_runs/.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RUNTIME_DB_PATH="${RESEARCH_AGENT_RUNTIME_DB_PATH:-$HOME/.local/share/research-agent/research_agent.db}"
RUNTIME_DB_URL="sqlite:///$RUNTIME_DB_PATH"

REGISTRY_PATH="${TIER_S_REGISTRY_PATH:-$ROOT_DIR/data/target_employers/tier_s_operational_sources_v1.csv}"
UNMATCHED_OUT="${TIER_S_UNMATCHED_OUT:-$ROOT_DIR/output/mapping/tier_s_operational_sources_unmatched.csv}"
QUEUES_OUT="${TIER_S_QUEUES_OUT:-$ROOT_DIR/output/mapping/tier_s_resolution_queues.csv}"
SUMMARY_OUT="${TIER_S_SUMMARY_OUT:-$ROOT_DIR/output/mapping/tier_s_resolution_summary.json}"
LOG_DIR="${TIER_S_LOG_DIR:-$ROOT_DIR/output/test_runs}"
SOURCE_VERSION="${TIER_S_SOURCE_VERSION:-tier_s_v1}"
SKIP_SYNC="${TIER_S_SKIP_SYNC:-0}"

mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/tier_s_operational_sources_$(date -u +%Y%m%d-%H%M%S).log"

log() {
  printf '%s\n' "$*"
}

{
  log "RESEARCH AGENT — TIER-S OPERATIONAL SOURCE CONTROL PLANE"
  log "project_root: $ROOT_DIR"
  log "registry:     $REGISTRY_PATH"
  log "runtime_db:   $RUNTIME_DB_PATH"
  log "log_file:     $LOG_FILE"
  log ""

  if [[ ! -f "$REGISTRY_PATH" ]]; then
    log "registry_missing: $REGISTRY_PATH"
    exit 1
  fi

  log "===== STEP 1/5 — VALIDATE MAPPING DATASET ====="
  RESEARCH_AGENT_DATABASE_URL="$RUNTIME_DB_URL" \
  uv run research-agent sync-tier-s-operational-sources \
    "$REGISTRY_PATH" \
    --unmatched-output "$UNMATCHED_OUT" \
    --queues-output "$QUEUES_OUT" \
    --summary-output "$SUMMARY_OUT" \
    --source-version "$SOURCE_VERSION" \
    --skip-sync \
    --database-url "$RUNTIME_DB_URL" 2>&1

  log ""
  log "===== STEP 2/5 — UNMATCHED EMPLOYERS REPORTED ====="
  if [[ -f "$UNMATCHED_OUT" ]]; then
    log "unmatched_employers:"
    awk -F',' 'NR>1 {print "  - "$1}' "$UNMATCHED_OUT" || true
  else
    log "unmatched_report_missing"
  fi

  log ""
  if [[ "$SKIP_SYNC" == "1" ]]; then
    log "===== STEP 3/5 — SYNC SKIPPED (TIER_S_SKIP_SYNC=1) ====="
  else
    log "===== STEP 3/5 — SYNC TO PERSISTENT DB ====="
    RESEARCH_AGENT_DATABASE_URL="$RUNTIME_DB_URL" \
    uv run research-agent sync-tier-s-operational-sources \
      "$REGISTRY_PATH" \
      --unmatched-output "$UNMATCHED_OUT" \
      --queues-output "$QUEUES_OUT" \
      --summary-output "$SUMMARY_OUT" \
      --source-version "$SOURCE_VERSION" \
      --database-url "$RUNTIME_DB_URL" 2>&1
  fi

  log ""
  log "===== STEP 4/5 — REPORTS REGENERATED ====="
  log "unmatched_csv:  $UNMATCHED_OUT"
  log "queues_csv:     $QUEUES_OUT"
  log "summary_json:   $SUMMARY_OUT"

  log ""
  log "===== STEP 5/5 — DONE ====="
  log "tier_s_operational_sources_status: ok"
} | tee -a "$LOG_FILE"
