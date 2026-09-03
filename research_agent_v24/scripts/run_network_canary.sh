#!/usr/bin/env bash
set -u -o pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <portal_id>" >&2
  exit 2
fi
PORTAL_ID="$1"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
STAMP="$(date '+%Y%m%d-%H%M%S')"
REPORT_DIR="${TEST_REPORT_DIR:-output/test_runs}"
mkdir -p "$REPORT_DIR"
REPORT_FILE="$REPORT_DIR/network_canary_portal_${PORTAL_ID}_${STAMP}.log"
exec > >(tee -a "$REPORT_FILE") 2>&1

echo "RESEARCH AGENT NETWORK CANARY"
echo "started_at: $(date -Iseconds)"
echo "portal_id: $PORTAL_ID"
echo "report_file: $REPORT_FILE"
echo

uv run research-agent prepare-canary-db --replace
PREP_RC=$?
echo "prepare_exit_code: $PREP_RC"
if [[ $PREP_RC -ne 0 ]]; then
  echo "REPORT READY: $REPORT_FILE"
  exit "$PREP_RC"
fi

echo "===== DRY RUN ====="
uv run research-agent scan-canary --portal-id "$PORTAL_ID" --dry-run
DRY_RC=$?
echo "dry_run_exit_code: $DRY_RC"
if [[ $DRY_RC -ne 0 ]]; then
  echo "REPORT READY: $REPORT_FILE"
  exit "$DRY_RC"
fi

echo "===== LIVE RUN ====="
uv run research-agent scan-canary --portal-id "$PORTAL_ID"
LIVE_RC=$?
echo "live_exit_code: $LIVE_RC"
echo "finished_at: $(date -Iseconds)"
echo "REPORT READY: $REPORT_FILE"
exit "$LIVE_RC"
