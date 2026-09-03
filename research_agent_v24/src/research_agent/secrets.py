"""Local API-key bootstrap helpers.

Secrets are never logged. A stable per-user env file survives extracted ZIP upgrades.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from research_agent.config import PERSISTENT_ENV_PATH, PROJECT_ROOT

_REQUIRED_NAMES = ("GEMINI_API_KEY", "OPENROUTER_API_KEY")


@dataclass(frozen=True)
class SecretsBootstrapResult:
    source: Path | None
    destination: Path
    installed: bool
    already_present: bool


def bootstrap_persistent_env(*, force: bool = False) -> SecretsBootstrapResult:
    destination = PERSISTENT_ENV_PATH.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.is_file() and _looks_useful(destination) and not force:
        _secure_mode(destination)
        return SecretsBootstrapResult(None, destination, False, True)

    candidates: list[Path] = []
    local = PROJECT_ROOT / ".env"
    if local.is_file() and _looks_useful(local):
        candidates.append(local)

    # Extracted versions usually live as siblings in Downloads (e.g. research_agent 5/6/7).
    parent = PROJECT_ROOT.parent
    for sibling in parent.iterdir() if parent.is_dir() else []:
        if sibling == PROJECT_ROOT or not sibling.is_dir():
            continue
        if not sibling.name.lower().startswith("research_agent"):
            continue
        candidate = sibling / ".env"
        if candidate.is_file() and _looks_useful(candidate):
            candidates.append(candidate)

    if not candidates:
        return SecretsBootstrapResult(None, destination, False, False)

    source = max(candidates, key=lambda p: p.stat().st_mtime)
    shutil.copy2(source, destination)
    _secure_mode(destination)
    return SecretsBootstrapResult(source.resolve(), destination, True, False)


def _looks_useful(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return any(values.get(name, "") for name in _REQUIRED_NAMES)


def _secure_mode(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        # Best effort on non-POSIX filesystems.
        pass
