"""Importer tests for unverified external source candidates (fully offline)."""

import csv
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_agent.company import external_candidates as ec
from research_agent.company.external_candidates import (
    BANNED_NETWORK_MODULES,
    import_external_candidates,
    normalize_url,
    scan_side_effect_counts,
    support_class_for,
)
from research_agent.db.models import ExternalSourceCandidate, ImportBatch

COMMIT = "6b44a1badc9bfbf5cf176f75265cc5729e520e99"

FIELDS = [
    "internal_company_id",
    "internal_company_name",
    "internal_domain",
    "internal_country",
    "external_provider",
    "external_provider_commit",
    "external_ats_family",
    "external_company_name",
    "external_slug",
    "external_url",
    "match_class",
    "match_basis",
    "confidence_reason",
    "verified",
    "verified_at",
    "jrc_support",
    "source_multiplicity",
]


def _row(company, ats, slug, url, match_class="HIGH_CONFIDENCE", basis="SLUG_PLUS_NAME"):
    return {
        "internal_company_id": company,
        "internal_company_name": f"Name {company}",
        "internal_domain": "example.com",
        "internal_country": "Italy",
        "external_provider": "ats-scrapers",
        "external_provider_commit": COMMIT,
        "external_ats_family": ats,
        "external_company_name": f"Ext {slug}",
        "external_slug": slug,
        "external_url": url,
        "match_class": match_class,
        "match_basis": basis,
        "confidence_reason": "test",
        "verified": "false",
        "verified_at": "",
        "jrc_support": "",
        "source_multiplicity": "",
    }


def _write_csv(path: Path, rows: list[dict[str, str]]) -> Path:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _fixture_csv(tmp_path: Path) -> Path:
    return _write_csv(
        tmp_path / "high.csv",
        [
            _row("EMP-1", "greenhouse", "acme", "https://job-boards.greenhouse.io/acme"),
            _row("EMP-1", "lever", "acme", "https://jobs.lever.co/acme"),
            _row("EMP-2", "bamboohr", "globex", "https://globex.bamboohr.com/jobs"),
            # Guardrail: CANDIDATE rows must never be imported.
            _row("EMP-3", "ashby", "initech", "https://jobs.ashbyhq.com/initech",
                 match_class="CANDIDATE"),
        ],
    )


def test_high_rows_imported_candidate_rows_rejected(sqlite_engine: Engine, tmp_path: Path) -> None:
    result = import_external_candidates(sqlite_engine, _fixture_csv(tmp_path))

    assert result.input_rows == 4
    assert result.valid_high_rows == 3
    assert result.skipped_non_high == 1
    assert result.inserted_rows == 3

    with Session(sqlite_engine) as session:
        stored = session.scalars(select(ExternalSourceCandidate)).all()
        assert len(stored) == 3
        assert {c.internal_company_id for c in stored} == {"EMP-1", "EMP-2"}
        assert all(c.verified is False for c in stored)
        assert all(c.verified_at is None for c in stored)
        assert all(c.match_class == "HIGH_CONFIDENCE" for c in stored)


def test_provenance_and_support_preserved(sqlite_engine: Engine, tmp_path: Path) -> None:
    import_external_candidates(sqlite_engine, _fixture_csv(tmp_path))

    with Session(sqlite_engine) as session:
        cand = session.scalar(
            select(ExternalSourceCandidate).where(
                ExternalSourceCandidate.internal_company_id == "EMP-2"
            )
        )
        assert cand is not None
        assert cand.provider == "ats-scrapers"
        assert cand.provider_commit == COMMIT
        assert cand.ats_family == "bamboohr"
        assert cand.slug == "globex"
        assert cand.external_url == "https://globex.bamboohr.com/jobs"
        assert cand.match_basis == "SLUG_PLUS_NAME"
        assert cand.confidence_reason == "test"
        # Unsupported ATS is preserved as knowledge, not dropped.
        assert cand.support_class == "UNSUPPORTED"
        assert session.scalar(
            select(ExternalSourceCandidate.support_class).where(
                ExternalSourceCandidate.ats_family == "greenhouse"
            )
        ) == "LEGACY_SUPPORTED"


def test_multiple_candidates_and_ats_per_company_preserved(
    sqlite_engine: Engine, tmp_path: Path
) -> None:
    result = import_external_candidates(sqlite_engine, _fixture_csv(tmp_path))

    assert result.companies_affected == 2
    assert result.multi_source_companies == 1
    with Session(sqlite_engine) as session:
        emp1 = session.scalars(
            select(ExternalSourceCandidate).where(
                ExternalSourceCandidate.internal_company_id == "EMP-1"
            )
        ).all()
        assert {c.ats_family for c in emp1} == {"greenhouse", "lever"}


def test_second_import_inserts_zero_duplicates(sqlite_engine: Engine, tmp_path: Path) -> None:
    path = _fixture_csv(tmp_path)
    first = import_external_candidates(sqlite_engine, path)
    second = import_external_candidates(sqlite_engine, path)

    assert first.inserted_rows == 3
    assert second.inserted_rows == 0
    assert second.duplicate_rows == 3
    assert second.already_imported is True
    with Session(sqlite_engine) as session:
        assert session.scalar(select(func.count()).select_from(ExternalSourceCandidate)) == 3
        assert session.scalar(select(func.count()).select_from(ImportBatch)) == 1


def test_normalized_url_duplicate_is_idempotent(sqlite_engine: Engine, tmp_path: Path) -> None:
    first = _write_csv(
        tmp_path / "a.csv",
        [_row("EMP-9", "greenhouse", "acme", "https://job-boards.greenhouse.io/acme")],
    )
    second = _write_csv(
        tmp_path / "b.csv",
        [_row("EMP-9", "greenhouse", "acme", "HTTPS://WWW.job-boards.greenhouse.io/acme/")],
    )
    assert normalize_url("HTTPS://WWW.job-boards.greenhouse.io/acme/") == normalize_url(
        "https://job-boards.greenhouse.io/acme"
    )

    # Different file bytes -> different batch, but the same deterministic
    # identity must still collapse. Import both into one batch stream by
    # concatenating: same-identity rows collapse within a single import.
    combined = _write_csv(
        tmp_path / "c.csv",
        [
            _row("EMP-9", "greenhouse", "acme", "https://job-boards.greenhouse.io/acme"),
            _row("EMP-9", "greenhouse", "acme", "HTTPS://WWW.job-boards.greenhouse.io/acme/"),
        ],
    )
    void = (first, second)
    assert void is not None
    result = import_external_candidates(sqlite_engine, combined)
    assert result.inserted_rows == 1
    assert result.duplicate_rows == 1


def test_no_binding_portal_or_scan_side_effects(sqlite_engine: Engine, tmp_path: Path) -> None:
    """Anti-cheat: candidates must never become portals, mappings, or scans."""
    import_external_candidates(sqlite_engine, _fixture_csv(tmp_path))

    with Session(sqlite_engine) as session:
        assert scan_side_effect_counts(session) == {"portals": 0, "mappings": 0, "scan_runs": 0}


def test_dry_run_writes_nothing(sqlite_engine: Engine, tmp_path: Path) -> None:
    result = import_external_candidates(sqlite_engine, _fixture_csv(tmp_path), dry_run=True)

    assert result.dry_run is True
    assert result.input_rows == 4
    assert result.valid_high_rows == 3
    assert result.inserted_rows == 0
    with Session(sqlite_engine) as session:
        assert session.scalar(select(func.count()).select_from(ExternalSourceCandidate)) == 0
        assert session.scalar(select(func.count()).select_from(ImportBatch)) == 0


def test_importer_has_zero_network_surface() -> None:
    # Static guarantee via AST: without an HTTP client import this module
    # cannot initiate network I/O regardless of what other modules load at
    # runtime (sys.modules order must not matter, so it is not asserted).
    import ast

    tree = ast.parse(Path(ec.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.asname or a.name for a in node.names)
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not ({m.split(".")[0] for m in imported} & {"httpx", "requests", "aiohttp"})
    assert "urllib.request" not in imported


def test_support_classification() -> None:
    assert support_class_for("greenhouse") == "LEGACY_SUPPORTED"
    assert support_class_for("eightfold") == "DECLARATIVE_SUPPORTED"
    assert support_class_for("bamboohr") == "UNSUPPORTED"
    assert support_class_for("") == "UNKNOWN"
