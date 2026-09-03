from pathlib import Path

import pytest
from sqlalchemy.engine import Engine

from research_agent.config import PROJECT_ROOT
from research_agent.db.session import create_db_engine


@pytest.fixture(scope="session")
def master_path() -> Path:
    return (
        PROJECT_ROOT
        / "data"
        / "company_universe"
        / "master_company_universe_v1_5_portal_resolution_wave5.csv"
    )


@pytest.fixture()
def sqlite_engine(tmp_path: Path) -> Engine:
    return create_db_engine(f"sqlite:///{tmp_path / 'test.db'}")
