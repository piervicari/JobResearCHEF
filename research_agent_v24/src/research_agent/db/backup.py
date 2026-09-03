"""Recoverable, integrity-checked SQLite backups for live scan gates."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class BackupResult:
    path: Path
    size_bytes: int
    sha256: str
    integrity_check: str


@dataclass(frozen=True)
class BackupRetentionPlan:
    directory: Path
    keep_last: int
    retained: tuple[Path, ...]
    deletable: tuple[Path, ...]
    orphan_sidecars: tuple[Path, ...]
    reclaimable_bytes: int


@dataclass(frozen=True)
class BackupPruneResult:
    deleted: tuple[Path, ...]
    reclaimed_bytes: int


def backup_sqlite_database(
    engine: Engine,
    *,
    destination: Path | None = None,
    backup_directory: Path | None = None,
) -> BackupResult:
    """Create an online SQLite backup without overwriting an existing artifact."""

    if engine.dialect.name != "sqlite" or not engine.url.database:
        raise ValueError("Automated backup currently supports file-backed SQLite only")
    if engine.url.database == ":memory:":
        raise ValueError("An in-memory SQLite database cannot be backed up by path")
    source_path = Path(engine.url.database).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"SQLite database does not exist: {source_path}")
    if destination is None:
        directory = (backup_directory or source_path.parent / "backups").resolve()
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        destination = directory / f"{source_path.stem}_{stamp}.db"
    destination = destination.expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite backup: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".partial")
    if partial.exists():
        raise FileExistsError(f"Refusing to overwrite partial backup: {partial}")

    try:
        with sqlite3.connect(source_path) as source, sqlite3.connect(partial) as target:
            source.backup(target)
            integrity = str(target.execute("PRAGMA integrity_check").fetchone()[0])
            if integrity != "ok":
                raise RuntimeError(f"Backup integrity_check failed: {integrity}")
        partial.replace(destination)
        _remove_sqlite_sidecars(partial)
    except Exception:
        if partial.exists():
            partial.unlink()
        _remove_sqlite_sidecars(partial)
        raise

    return BackupResult(
        path=destination,
        size_bytes=destination.stat().st_size,
        sha256=_sha256(destination),
        integrity_check="ok",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def plan_backup_retention(
    backup_directory: Path,
    *,
    keep_last: int = 3,
) -> BackupRetentionPlan:
    """Return a deterministic dry-run plan; no files are removed."""

    if keep_last < 1:
        raise ValueError("keep_last must be at least 1")
    directory = backup_directory.expanduser().resolve()
    if not directory.is_dir():
        raise FileNotFoundError(f"Backup directory does not exist: {directory}")
    backups = sorted(
        (path.resolve() for path in directory.glob("*.db") if path.is_file()),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
        reverse=True,
    )
    retained = tuple(backups[:keep_last])
    deletable = tuple(backups[keep_last:])
    referenced = {path for backup in backups for path in _sqlite_sidecars(backup)}
    orphan_sidecars = tuple(
        sorted(
            (
                path.resolve()
                for path in directory.iterdir()
                if path.is_file()
                and (
                    path.name.endswith(".db-shm")
                    or path.name.endswith(".db-wal")
                    or path.name.endswith(".db.partial-shm")
                    or path.name.endswith(".db.partial-wal")
                )
                and path.resolve() not in referenced
            ),
            key=lambda path: path.name,
        )
    )
    removal = set(deletable) | {
        sidecar for backup in deletable for sidecar in _sqlite_sidecars(backup) if sidecar.exists()
    }
    removal.update(orphan_sidecars)
    return BackupRetentionPlan(
        directory=directory,
        keep_last=keep_last,
        retained=retained,
        deletable=deletable,
        orphan_sidecars=orphan_sidecars,
        reclaimable_bytes=sum(path.stat().st_size for path in removal),
    )


def apply_backup_retention(plan: BackupRetentionPlan) -> BackupPruneResult:
    """Apply an inspected retention plan without following paths outside its directory."""

    targets = set(plan.deletable) | set(plan.orphan_sidecars)
    targets.update(
        sidecar
        for backup in plan.deletable
        for sidecar in _sqlite_sidecars(backup)
        if sidecar.exists()
    )
    deleted: list[Path] = []
    reclaimed = 0
    for path in sorted(targets, key=lambda item: item.name):
        resolved = path.resolve()
        if resolved.parent != plan.directory:
            raise ValueError(f"Refusing to prune path outside backup directory: {resolved}")
        if not resolved.is_file():
            continue
        reclaimed += resolved.stat().st_size
        resolved.unlink()
        deleted.append(resolved)
    return BackupPruneResult(deleted=tuple(deleted), reclaimed_bytes=reclaimed)


def _sqlite_sidecars(path: Path) -> tuple[Path, Path]:
    return (Path(f"{path}-shm"), Path(f"{path}-wal"))


def _remove_sqlite_sidecars(path: Path) -> None:
    for sidecar in _sqlite_sidecars(path):
        if sidecar.exists():
            sidecar.unlink()
