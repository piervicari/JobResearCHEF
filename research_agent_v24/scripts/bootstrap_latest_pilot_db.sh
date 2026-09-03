#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
uv run python - <<'PY'
from pathlib import Path
import shutil
root = Path.cwd().resolve()
dest = root / 'data' / 'pilot' / 'research_agent_pilot.db'
candidates = []
for sibling in root.parent.iterdir():
    if not sibling.is_dir() or sibling.resolve() == root:
        continue
    if not sibling.name.lower().startswith('research_agent'):
        continue
    candidate = sibling / 'data' / 'pilot' / 'research_agent_pilot.db'
    if candidate.is_file() and candidate.stat().st_size > 0:
        candidates.append(candidate)
if not candidates:
    raise SystemExit('No previous pilot DB found in sibling research_agent* folders')
source = max(candidates, key=lambda p: p.stat().st_mtime)
dest.parent.mkdir(parents=True, exist_ok=True)
for suffix in ('', '-wal', '-shm'):
    p = Path(f'{dest}{suffix}')
    if p.exists():
        p.unlink()
shutil.copy2(source, dest)
print(f'pilot_db_imported_from: {source}')
print(f'pilot_db_destination: {dest}')
PY

# Imported pilot databases may come from an older project version. Upgrade the
# local SQLite schema additively before any command tries to query new columns.
uv run research-agent init-db --database-url sqlite:///data/pilot/research_agent_pilot.db >/dev/null
echo "schema_migration: ok"
