"""Runtime DB resolution convergence (ADR 0042).

Pins: the default Settings DB is the canonical persistent path; the central
resolver expands it against the runtime HOME so CLI/scanner/dashboard/sync
all open the same file; explicit overrides still win. HOME-isolated: never
touches the developer's real HOME or either real database.
"""
from __future__ import annotations

import os
from pathlib import Path

from research_agent.config import AppSettings
from research_agent.db.session import create_db_engine, normalize_database_url

CANONICAL_URL = "sqlite:///~/.local/share/research-agent/research_agent.db"


def test_default_database_url_is_canonical_persistent_path(monkeypatch) -> None:
    monkeypatch.delenv("RESEARCH_AGENT_DATABASE_URL", raising=False)
    assert AppSettings().database_url == CANONICAL_URL


def test_settings_yaml_agrees_with_code_default() -> None:
    import yaml

    root = Path(__file__).resolve().parents[1]
    values = yaml.safe_load((root / "config" / "settings.yaml").read_text())
    assert values["database_url"] == CANONICAL_URL


def test_normalize_expands_home_and_passes_through(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    resolved = normalize_database_url(CANONICAL_URL)
    assert resolved == f"sqlite:///{tmp_path}/.local/share/research-agent/research_agent.db"
    assert normalize_database_url("sqlite:///relative.db") == "sqlite:///relative.db"
    assert normalize_database_url("sqlite:///:memory:") == "sqlite:///:memory:"
    assert normalize_database_url("postgresql://db/x") == "postgresql://db/x"


def test_create_db_engine_opens_canonical_file_under_isolated_home(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    engine = create_db_engine(CANONICAL_URL)
    assert engine.url.database == str(
        tmp_path / ".local" / "share" / "research-agent" / "research_agent.db"
    )
    with engine.connect():
        pass
    assert Path(engine.url.database).is_file()
    assert not (tmp_path / "~").exists()
    engine.dispose()


def test_explicit_database_url_override_still_wins(tmp_path: Path) -> None:
    from research_agent.cli import _engine

    custom = tmp_path / "custom.db"
    engine = _engine(f"sqlite:///{custom}")
    assert engine.url.database == str(custom)
    with engine.connect():
        pass
    assert custom.is_file()
    engine.dispose()
