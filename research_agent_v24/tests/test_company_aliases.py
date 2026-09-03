import csv
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_agent.company.aliases import (
    ALIAS_HEADERS,
    import_company_aliases,
    propose_company_aliases,
)
from research_agent.company.clustering import PortalClusterResolver
from research_agent.company.importer import import_master
from research_agent.db.models import CompanyAlias


def _write_aliases(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ALIAS_HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def test_only_verified_aliases_resolve_external_company(
    sqlite_engine: Engine,
    master_path: Path,
    tmp_path: Path,
) -> None:
    import_master(sqlite_engine, master_path)
    artifact = tmp_path / "aliases.csv"
    _write_aliases(
        artifact,
        [
            {
                "Alias": "Amazon Web Services",
                "Corporate Cluster ID": "CG-1E17FD881E",
                "Status": "VERIFIED",
                "Provenance": "fixture review",
                "Evidence Reference": "fixture://master-row",
                "Reason": "reviewed variant",
            },
            {
                "Alias": "AWS",
                "Corporate Cluster ID": "CG-1E17FD881E",
                "Status": "PROPOSED",
                "Provenance": "fixture fuzzy candidate",
                "Evidence Reference": "",
                "Reason": "not yet reviewed",
            },
        ],
    )
    first = import_company_aliases(sqlite_engine, artifact, source_version="aliases-v1")
    second = import_company_aliases(sqlite_engine, artifact, source_version="aliases-v1")
    assert first.created == 2
    assert second.already_imported is True

    with Session(sqlite_engine) as session:
        resolver = PortalClusterResolver(session)
        verified = resolver.resolve_company("Amazon Web Services")
        proposed = resolver.resolve_company("AWS")
    assert verified.corporate_cluster_id == "CG-1E17FD881E"
    assert verified.method == "global_verified_company_alias"
    assert proposed.corporate_cluster_id is None


def test_fuzzy_candidates_are_read_only(
    sqlite_engine: Engine,
    master_path: Path,
) -> None:
    import_master(sqlite_engine, master_path)
    with Session(sqlite_engine) as session:
        before = session.scalar(select(func.count()).select_from(CompanyAlias)) or 0
    proposals = propose_company_aliases(
        sqlite_engine, "Price Waterhouse Cooper", threshold=0.7, limit=3
    )
    with Session(sqlite_engine) as session:
        after = session.scalar(select(func.count()).select_from(CompanyAlias)) or 0
    assert proposals
    assert proposals[0].corporate_cluster_id == "CG-C3A0759193"
    assert before == after == 0
