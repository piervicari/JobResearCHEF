import sqlite3
from pathlib import Path

import pytest

from research_agent.db.recovery import restore_and_verify_sqlite_backup


def test_restore_verifies_checksum_integrity_and_table_counts(tmp_path: Path) -> None:
    backup = tmp_path / "backup.db"
    with sqlite3.connect(backup) as connection:
        connection.execute("CREATE TABLE evidence (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        connection.executemany(
            "INSERT INTO evidence(value) VALUES (?)",
            [("one",), ("two",)],
        )
    restored = tmp_path / "restored.db"

    result = restore_and_verify_sqlite_backup(backup, restored)

    assert result.integrity_check == "ok"
    assert result.backup_sha256 == result.restored_sha256
    assert result.table_counts == {"evidence": 2}
    with pytest.raises(FileExistsError):
        restore_and_verify_sqlite_backup(backup, restored)
