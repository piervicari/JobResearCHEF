"""Non-destructive SQLite restore verification for operational recovery drills."""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RecoveryResult:
    backup_path: Path
    restored_path: Path
    backup_sha256: str
    restored_sha256: str
    integrity_check: str
    table_counts: dict[str, int]


def restore_and_verify_sqlite_backup(backup: Path, destination: Path) -> RecoveryResult:
    """Copy a backup to a new path and prove integrity and exact table counts."""

    source = backup.expanduser().resolve()
    target = destination.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"SQLite backup does not exist: {source}")
    if target.exists():
        raise FileExistsError(f"Refusing to overwrite recovery destination: {target}")
    if source == target:
        raise ValueError("Recovery destination must differ from the backup path")
    target.parent.mkdir(parents=True, exist_ok=True)

    source_counts = _table_counts(source)
    shutil.copy2(source, target)
    try:
        with sqlite3.connect(target) as restored:
            integrity = str(restored.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity != "ok":
            raise RuntimeError(f"Restored database integrity_check failed: {integrity}")
        restored_counts = _table_counts(target)
        if restored_counts != source_counts:
            raise RuntimeError("Restored database table counts differ from the backup")
        source_sha = _sha256(source)
        target_sha = _sha256(target)
        if target_sha != source_sha:
            raise RuntimeError("Restored database checksum differs from the backup")
    except Exception:
        if target.exists():
            target.unlink()
        raise

    return RecoveryResult(
        backup_path=source,
        restored_path=target,
        backup_sha256=source_sha,
        restored_sha256=target_sha,
        integrity_check="ok",
        table_counts=restored_counts,
    )


def render_recovery_report(result: RecoveryResult) -> str:
    lines = [
        "# SQLite recovery validation",
        "",
        f"- Backup: `{result.backup_path}`",
        f"- Restored copy: `{result.restored_path}`",
        f"- SHA-256: `{result.backup_sha256}`",
        f"- Integrity check: `{result.integrity_check}`",
        f"- Exact checksum match: `{result.backup_sha256 == result.restored_sha256}`",
        "",
        "## Table counts",
        "",
        "| Table | Rows |",
        "|---|---:|",
    ]
    lines.extend(f"| `{table}` | {count:,} |" for table, count in result.table_counts.items())
    return "\n".join(lines) + "\n"


def _table_counts(path: Path) -> dict[str, int]:
    with sqlite3.connect(path) as connection:
        tables = [
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        return {
            table: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            for table in tables
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
