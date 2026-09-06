"""Offline import of external-registry source candidates (evidence, not bindings).

Reads the HIGH_CONFIDENCE CSV produced by the offline overlap step and stores
rows as unverified evidence in ``external_source_candidates``. Fully offline:
stdlib CSV/hashlib plus ``urllib.parse`` for URL normalization only. No HTTP
client is imported anywhere in this module. Nothing here creates portals,
bindings, mappings, or scan runs.
"""

from __future__ import annotations

import csv
import hashlib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from research_agent.db.migrations import create_schema
from research_agent.db.models import (
    ClusterPortalMapping,
    ExternalSourceCandidate,
    ImportBatch,
    Portal,
    ScanRun,
    utc_now,
)

SOURCE_KIND = "external_source_candidates"
HIGH_CONFIDENCE = "HIGH_CONFIDENCE"

# Offline support map. Mirrors the legacy adapter set
# (sources/ats/*.py) and the declarative v0.1 specs (beesite, eightfold).
# Display aid only: it never changes import behavior.
_LEGACY_ATS = frozenset(
    {
        "ashby",
        "avature",
        "google",
        "greenhouse",
        "lever",
        "oracle",
        "phenom",
        "radancy",
        "smartrecruiters",
        "successfactors",
        "workday",
    }
)
_DECLARATIVE_ATS = frozenset({"beesite", "eightfold"})

BANNED_NETWORK_MODULES = ("httpx", "requests", "aiohttp", "urllib.request")


def support_class_for(ats_family: str) -> str:
    family = (ats_family or "").strip().lower()
    legacy = family in _LEGACY_ATS
    declarative = family in _DECLARATIVE_ATS
    if legacy and declarative:
        return "BOTH"
    if legacy:
        return "LEGACY_SUPPORTED"
    if declarative:
        return "DECLARATIVE_SUPPORTED"
    if not family:
        return "UNKNOWN"
    return "UNSUPPORTED"


def normalize_url(value: str) -> str:
    """Deterministic URL identity: lowercase scheme/host, strip www/trailing slash."""
    text = (value or "").strip().strip("'\"")
    if not text:
        return ""
    if "://" not in text:
        text = "https://" + text
    try:
        parts = urlsplit(text)
    except ValueError:
        return text.lower().rstrip("/")
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = (parts.path or "").rstrip("/") or ""
    query = f"?{parts.query}" if parts.query else ""
    return urlunsplit((parts.scheme.lower() or "https", host, path, query, ""))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_candidates(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


@dataclass
class ExternalCandidateImportResult:
    import_batch_id: int
    source_sha256: str
    already_imported: bool
    dry_run: bool = False
    input_rows: int = 0
    valid_high_rows: int = 0
    skipped_non_high: int = 0
    duplicate_rows: int = 0
    inserted_rows: int = 0
    companies_affected: int = 0
    multi_source_companies: int = 0
    ats_distribution: dict[str, int] = field(default_factory=dict)
    support_distribution: dict[str, int] = field(default_factory=dict)


def _row_identity(row: dict[str, str]) -> tuple[str, str, str, str, str] | None:
    company = (row.get("internal_company_id") or "").strip()
    provider = (row.get("external_provider") or "").strip()
    ats = (row.get("external_ats_family") or "").strip().lower()
    url = normalize_url(row.get("external_url") or "")
    slug = (row.get("external_slug") or row.get("external_slug / tenant id") or "").strip()
    if not company or not provider or not ats or not url:
        return None
    return (company, provider, ats, url, slug)


def import_external_candidates(
    engine: Engine, path: Path, *, dry_run: bool = False
) -> ExternalCandidateImportResult:
    """Import HIGH_CONFIDENCE external candidates as unverified evidence.

    Idempotent on the deterministic identity (company, provider, ATS,
    normalized URL, slug). Non-HIGH rows are skipped and reported. Dry runs
    write nothing.
    """
    create_schema(engine)
    resolved = path.expanduser().resolve()
    source_sha = file_sha256(resolved)
    rows = read_candidates(resolved)

    high_rows = [r for r in rows if (r.get("match_class") or "").strip() == HIGH_CONFIDENCE]
    skipped = len(rows) - len(high_rows)

    identities: dict[tuple[str, str, str, str, str], dict[str, str]] = {}
    valid_identity_rows = 0
    for row in high_rows:
        identity = _row_identity(row)
        if identity is None:
            skipped += 1
            continue
        valid_identity_rows += 1
        identities.setdefault(identity, row)

    result = ExternalCandidateImportResult(
        import_batch_id=0,
        source_sha256=source_sha,
        already_imported=False,
        dry_run=dry_run,
        input_rows=len(rows),
        valid_high_rows=len(high_rows),
        skipped_non_high=skipped,
    )

    with Session(engine) as session, session.begin():
        batch = session.scalar(
            select(ImportBatch).where(
                ImportBatch.source_kind == SOURCE_KIND,
                ImportBatch.source_sha256 == source_sha,
            )
        )
        if batch is None and not dry_run:
            batch = ImportBatch(
                source_kind=SOURCE_KIND,
                source_filename=resolved.name,
                source_path=str(resolved),
                source_sha256=source_sha,
                source_version=(high_rows[0].get("external_provider_commit") or "").strip()
                if high_rows
                else "",
                status="RUNNING",
            )
            session.add(batch)
            session.flush()

        if batch is not None:
            result.import_batch_id = batch.id
            existing = {
                row
                for row in session.execute(
                    select(
                        ExternalSourceCandidate.internal_company_id,
                        ExternalSourceCandidate.provider,
                        ExternalSourceCandidate.ats_family,
                        ExternalSourceCandidate.normalized_external_url,
                        ExternalSourceCandidate.slug,
                    ).where(ExternalSourceCandidate.import_batch_id == batch.id)
                ).all()
            }
        else:
            # Dry run on a file never imported: check against all prior imports
            # of the same provider so duplicate counts stay truthful.
            existing = set()

        to_insert = {key: row for key, row in identities.items() if key not in existing}
        result.duplicate_rows = (valid_identity_rows - len(identities)) + (
            len(identities) - len(to_insert)
        )
        result.inserted_rows = 0 if dry_run else len(to_insert)

        for (company, provider, ats, url, slug), row in sorted(to_insert.items()):
            support = support_class_for(ats)
            if not dry_run:
                assert batch is not None
                session.add(
                    ExternalSourceCandidate(
                        internal_company_id=company,
                        internal_company_name=(row.get("internal_company_name") or "").strip(),
                        internal_domain=(row.get("internal_domain") or "").strip(),
                        internal_country=(row.get("internal_country") or "").strip(),
                        provider=provider,
                        provider_commit=(row.get("external_provider_commit") or "").strip(),
                        ats_family=ats,
                        external_company_name=(row.get("external_company_name") or "").strip(),
                        slug=slug,
                        external_url=(row.get("external_url") or "").strip(),
                        normalized_external_url=url,
                        match_class=HIGH_CONFIDENCE,
                        match_basis=(row.get("match_basis") or "").strip(),
                        confidence_reason=(row.get("confidence_reason") or "").strip(),
                        support_class=support,
                        verified=False,
                        verified_at=None,
                        import_batch_id=batch.id,
                    )
                )

        # Distribution stats cover the full valid HIGH set, not just inserts,
        # so dry-run and repeat runs report the same picture.
        full_ats: Counter[str] = Counter()
        full_support: Counter[str] = Counter()
        full_companies: Counter[str] = Counter()
        for key in identities:
            full_ats[key[2]] += 1
            full_support[support_class_for(key[2])] += 1
            full_companies[key[0]] += 1
        result.ats_distribution = dict(sorted(full_ats.items()))
        result.support_distribution = dict(sorted(full_support.items()))
        result.companies_affected = len(full_companies)
        result.multi_source_companies = sum(1 for n in full_companies.values() if n > 1)

        if batch is not None and not dry_run:
            result.already_imported = not to_insert and batch.status == "COMPLETED"
            batch.status = "COMPLETED"
            batch.finished_at = utc_now()
            batch.row_count = len(identities)

    return result


def scan_side_effect_counts(session: Session) -> dict[str, int]:
    """Counts proving the import never promotes anything to the scan path."""
    return {
        "portals": session.scalar(select(func.count()).select_from(Portal)) or 0,
        "mappings": session.scalar(select(func.count()).select_from(ClusterPortalMapping)) or 0,
        "scan_runs": session.scalar(select(func.count()).select_from(ScanRun)) or 0,
    }
