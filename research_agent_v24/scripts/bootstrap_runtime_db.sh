#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RUNTIME_DB_PATH="${RESEARCH_AGENT_RUNTIME_DB_PATH:-$HOME/.local/share/research-agent/research_agent.db}"
mkdir -p "$(dirname "$RUNTIME_DB_PATH")"

if [[ ! -f "$RUNTIME_DB_PATH" ]]; then
  SOURCE_DB="$(uv run python - <<'PY'
from pathlib import Path

root = Path.cwd().resolve()
downloads = root.parent
candidates = []
for sibling in downloads.glob('research_agent*'):
    try:
        if sibling.resolve() == root:
            continue
    except OSError:
        continue
    db = sibling / 'data' / 'pilot' / 'research_agent_pilot.db'
    if db.is_file():
        candidates.append(db)
if not candidates:
    raise SystemExit(0)
latest = max(candidates, key=lambda p: p.stat().st_mtime)
print(latest)
PY
)"

  if [[ -n "$SOURCE_DB" && -f "$SOURCE_DB" ]]; then
    cp "$SOURCE_DB" "$RUNTIME_DB_PATH"
    echo "runtime_db_seeded_from: $SOURCE_DB"
  elif [[ -f "$ROOT_DIR/data/research_agent.db" ]]; then
    cp "$ROOT_DIR/data/research_agent.db" "$RUNTIME_DB_PATH"
    echo "runtime_db_seeded_from: $ROOT_DIR/data/research_agent.db"
  else
    echo "runtime_db_seeded_from: none (new database)"
  fi
else
  echo "runtime_db_status: existing"
fi

RUNTIME_DB_URL="sqlite:///$RUNTIME_DB_PATH"
RESEARCH_AGENT_RUNTIME_DATABASE_URL="$RUNTIME_DB_URL" uv run python - <<'PY'
import os
from sqlalchemy import create_engine
from research_agent.db.migrations import create_schema

url = os.environ['RESEARCH_AGENT_RUNTIME_DATABASE_URL']
engine = create_engine(url)
create_schema(engine)
with engine.connect() as conn:
    integrity = conn.exec_driver_sql('PRAGMA integrity_check').scalar_one()
    source_jobs = conn.exec_driver_sql('SELECT COUNT(*) FROM source_jobs').scalar_one()
    analyses = conn.exec_driver_sql('SELECT COUNT(*) FROM job_ai_analyses').scalar_one()
print(f"schema_migration: ok")
print(f"integrity_check: {integrity}")
print(f"source_jobs: {source_jobs}")
print(f"job_ai_analyses: {analyses}")
PY

echo "runtime_db_path: $RUNTIME_DB_PATH"
echo "runtime_db_url: $RUNTIME_DB_URL"
