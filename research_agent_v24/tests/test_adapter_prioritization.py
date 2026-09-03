from pathlib import Path

from sqlalchemy.engine import Engine

from research_agent.company.adapter_prioritization import (
    rank_fallback_portals,
    write_adapter_candidate_csv,
)
from research_agent.company.importer import import_master


def test_fallback_ranking_is_complete_deterministic_and_non_mutating(
    sqlite_engine: Engine,
    master_path: Path,
    tmp_path: Path,
) -> None:
    import_master(sqlite_engine, master_path)
    first = rank_fallback_portals(sqlite_engine)
    second = rank_fallback_portals(sqlite_engine)
    output = tmp_path / "ranking.csv"
    write_adapter_candidate_csv(first, output)

    assert first == second
    assert len(first) > 300
    assert [row.rank for row in first] == list(range(1, len(first) + 1))
    assert all(row.jobs_url.startswith("https://") for row in first)
    assert output.read_text(encoding="utf-8").startswith("rank,portal_id,company,")
