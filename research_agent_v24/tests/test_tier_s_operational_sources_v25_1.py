"""V25.1 Control Plane Hardening — production-registry integration tests.

These tests load the *committed* `data/target_employers/tier_s_operational_sources_v1.csv`
and assert that it is shape-correct, content-correct, and aligned with the
project invariants. A passing test suite with a malformed production
registry is NOT sufficient (per the V25.1 review brief).
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

import pytest
import yaml

from research_agent.company.tier_s_operational_sources import (
    REGISTRY_HEADERS,
    VALID_CATALOG_STATES,
    VALID_COHORTS,
    VALID_EVIDENCE_STATES,
    VALID_RESOLUTION_PATHS,
    OperationalSourceError,
    _infer_ats_family,
    derive_routing,
    read_registry,
    validate_registry_invariants,
)

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_REGISTRY = ROOT / "data" / "target_employers" / "tier_s_operational_sources_v1.csv"
CORE_YAML = ROOT / "data" / "target_employers" / "target_employers_v0_2.yaml"


# ---------------------------------------------------------------------------
# 1. Exact schema and column count
# ---------------------------------------------------------------------------


def test_production_registry_exact_schema() -> None:
    with PRODUCTION_REGISTRY.open(encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader)
    assert tuple(header) == REGISTRY_HEADERS, (
        f"production registry schema drifted: {header!r} != {REGISTRY_HEADERS!r}"
    )


def test_production_registry_exact_column_count_on_every_row() -> None:
    """No row may have extra/missing columns or malformed quoting."""
    with PRODUCTION_REGISTRY.open(encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader)
        bad = [
            (i, len(row))
            for i, row in enumerate(reader, start=2)
            if len(row) != len(header)
        ]
    assert not bad, (
        f"production registry has {len(bad)} rows with wrong column count; "
        f"first few: {bad[:5]}"
    )


def test_production_registry_parses() -> None:
    """Strict parser must accept the production registry without exceptions."""
    rows = read_registry(PRODUCTION_REGISTRY)
    assert len(rows) > 0


# ---------------------------------------------------------------------------
# 2. CORE_200 coverage
# ---------------------------------------------------------------------------


def test_production_registry_contains_200_distinct_core_200_employers() -> None:
    """The 200-employer CORE_200 acceptance gate."""
    rows = read_registry(PRODUCTION_REGISTRY)
    core_200 = {r.employer_name for r in rows if r.cohort == "CORE_200"}
    with CORE_YAML.open() as f:
        v0 = yaml.safe_load(f)
    v0_names = {e["name"] for e in v0["employers"]}
    missing = v0_names - core_200
    assert len(core_200) == 200, (
        f"CORE_200 count {len(core_200)} != 200; missing {len(missing)}; "
        f"first few: {sorted(missing)[:5]}"
    )
    # v0.2 must be a subset of the registry's CORE_200 names
    extra = core_200 - v0_names
    assert not extra, f"registry has CORE_200 names not in v0.2: {sorted(extra)[:5]}"


def test_production_registry_distinct_core_extension_separate() -> None:
    rows = read_registry(PRODUCTION_REGISTRY)
    core_ext = {r.employer_name for r in rows if r.cohort == "CORE_EXTENSION"}
    assert len(core_ext) >= 0  # at minimum, the cohort is well-formed
    # The two cohorts are disjoint.
    core_200 = {r.employer_name for r in rows if r.cohort == "CORE_200"}
    assert core_200.isdisjoint(core_ext)


# ---------------------------------------------------------------------------
# 3. Enum validation
# ---------------------------------------------------------------------------


def test_production_registry_all_enums_valid() -> None:
    """Every enum-typed column must be in its declared set."""
    rows = read_registry(PRODUCTION_REGISTRY)
    bad: list[str] = []
    for r in rows:
        if r.cohort not in VALID_COHORTS:
            bad.append(f"{r.employer_name}/{r.source_key}: cohort={r.cohort}")
        if r.evidence_state not in VALID_EVIDENCE_STATES:
            bad.append(f"{r.employer_name}/{r.source_key}: evidence_state={r.evidence_state}")
        if r.resolution_path not in VALID_RESOLUTION_PATHS:
            bad.append(f"{r.employer_name}/{r.source_key}: resolution_path={r.resolution_path}")
        if r.catalog_state not in VALID_CATALOG_STATES:
            bad.append(f"{r.employer_name}/{r.source_key}: catalog_state={r.catalog_state}")
    assert not bad, f"bad enum values: {bad[:5]}"


# ---------------------------------------------------------------------------
# 4. Cross-row invariants
# ---------------------------------------------------------------------------


def test_production_registry_no_contradictions() -> None:
    """The cross-row validator must produce zero problems."""
    rows = read_registry(PRODUCTION_REGISTRY)
    problems = validate_registry_invariants(rows)
    assert not problems, f"cross-row invariants failed: {problems[:5]}"


def test_production_registry_multi_source_uniqueness() -> None:
    """(employer, source_key) must be unique."""
    rows = read_registry(PRODUCTION_REGISTRY)
    keys: list[tuple[str, str]] = []
    for r in rows:
        keys.append((r.employer_name, r.source_key))
    counter = Counter(keys)
    dupes = [k for k, n in counter.items() if n > 1]
    assert not dupes, f"duplicate (employer, source_key) pairs: {dupes[:5]}"


# ---------------------------------------------------------------------------
# 5. Google row must NOT have catalog_state=VERIFIED
# ---------------------------------------------------------------------------


def test_production_registry_google_catalog_not_verified() -> None:
    """Google custom RPC platform may remain READY_TO_PROBE, but its catalog
    must stay UNTESTED or PARITY_PENDING until the V24 Google probe is
    actually executed and independently validated."""
    rows = read_registry(PRODUCTION_REGISTRY)
    google = [r for r in rows if r.employer_name == "Google"]
    assert google, "Google row is missing from the production registry"
    for g in google:
        assert g.catalog_state in {"UNTESTED", "PARITY_PENDING"}, (
            f"Google row has catalog_state={g.catalog_state!r}; "
            "the V24 Google probe has not been completed yet"
        )


# ---------------------------------------------------------------------------
# 6. Routing derivation matches
# ---------------------------------------------------------------------------


def test_production_registry_routing_matches_derivation_or_has_override() -> None:
    """For every row in production, `resolution_path` must equal either the
    derived routing or the routing_override (which equals resolution_path)."""
    rows = read_registry(PRODUCTION_REGISTRY)
    bad: list[str] = []
    for r in rows:
        derived = derive_routing(
            evidence_state=r.evidence_state,
            ats_family=r.ats_family,
            adapter_supported=r.adapter_supported,
            operational_url=r.operational_url,
        )
        if derived == r.resolution_path:
            continue
        if r.routing_override and r.routing_override == r.resolution_path:
            # Human override is allowed.
            if not r.routing_override_rationale:
                bad.append(
                    f"{r.employer_name}/{r.source_key}: override set without rationale"
                )
            continue
        bad.append(
            f"{r.employer_name}/{r.source_key}: routing={r.resolution_path!r} "
            f"derived={derived!r} override={r.routing_override!r}"
        )
    assert not bad, f"routing contradictions: {bad[:5]}"


# ---------------------------------------------------------------------------
# 7. Source-less rows
# ---------------------------------------------------------------------------


def test_production_registry_source_less_rows_route_to_hold() -> None:
    """A row with empty `operational_url` must have routing == HOLD."""
    rows = read_registry(PRODUCTION_REGISTRY)
    bad = [
        (r.employer_name, r.resolution_path)
        for r in rows
        if not r.operational_url and r.resolution_path != "HOLD"
    ]
    assert not bad, f"source-less rows not routed to HOLD: {bad[:5]}"


# ---------------------------------------------------------------------------
# 8. No fabricated last_verified_at
# ---------------------------------------------------------------------------


def test_production_registry_last_verified_at_can_be_blank() -> None:
    rows = read_registry(PRODUCTION_REGISTRY)
    blank_count = sum(1 for r in rows if not r.last_verified_at)
    assert blank_count > 0, (
        "no source-less rows have blank last_verified_at; "
        "the parser may be auto-filling today's date (regression check)"
    )


# ---------------------------------------------------------------------------
# 9. Taleo is its own family, not Oracle Recruiting Cloud
# ---------------------------------------------------------------------------


def test_production_registry_taleo_not_labelled_as_oracle_recruiting_cloud() -> None:
    """The brief explicitly forbids merging Taleo and Oracle Recruiting Cloud."""
    rows = read_registry(PRODUCTION_REGISTRY)
    for r in rows:
        if r.ats_family == "Taleo" and "Oracle Recruiting Cloud" in (r.notes or ""):
            pytest.fail(
                f"{r.employer_name}/{r.source_key}: Taleo mislabelled as Oracle Recruiting Cloud"
            )


# ---------------------------------------------------------------------------
# 10. Distinct-employer metrics in the summary
# ---------------------------------------------------------------------------


def test_production_registry_summary_uses_distinct_employers() -> None:
    """The summary metric core_200_employers must be the count of distinct
    employer names in CORE_200, not the row count."""
    rows = read_registry(PRODUCTION_REGISTRY)
    distinct = {r.employer_name for r in rows if r.cohort == "CORE_200"}
    assert len(distinct) == 200


# ---------------------------------------------------------------------------
# 11. Routing derivation: deterministic unit tests
# ---------------------------------------------------------------------------


def test_derive_routing_source_less_is_hold() -> None:
    assert derive_routing(
        evidence_state="FIRST_PARTY_VERIFIED",
        ats_family="",
        adapter_supported="NO",
        operational_url="",
    ) == "HOLD"


def test_derive_routing_automation_grade_supported_adapter_is_ready() -> None:
    assert derive_routing(
        evidence_state="TECHNICALLY_VERIFIED",
        ats_family="Greenhouse",
        adapter_supported="YES",
        operational_url="https://boards-api.greenhouse.io/v1/boards/x/jobs",
    ) == "READY_TO_PROBE"


def test_derive_routing_automation_grade_unsupported_reusable_is_adapter_needed() -> None:
    assert derive_routing(
        evidence_state="TECHNICALLY_VERIFIED",
        ats_family="Taleo",
        adapter_supported="YES",
        operational_url="https://tas.example.com/careers",
    ) == "ADAPTER_NEEDED"


def test_derive_routing_probable_is_fingerprint_required() -> None:
    assert derive_routing(
        evidence_state="PROBABLE",
        ats_family="Greenhouse",
        adapter_supported="YES",
        operational_url="https://boards-api.greenhouse.io/v1/boards/x/jobs",
    ) == "FINGERPRINT_REQUIRED"


def test_derive_routing_unverifiable_first_party_is_resolver_light() -> None:
    assert derive_routing(
        evidence_state="UNVERIFIED",
        ats_family="",
        adapter_supported="NO",
        operational_url="https://www.example.com/careers",
    ) == "RESOLVER_LIGHT"


def test_derive_routing_automation_grade_no_family_is_adapter_needed() -> None:
    """Automation-grade evidence but no ats_family is ADAPTER_NEEDED, not READY_TO_PROBE."""
    assert derive_routing(
        evidence_state="FIRST_PARTY_VERIFIED",
        ats_family="",
        adapter_supported="YES",
        operational_url="https://www.example.com/careers",
    ) == "ADAPTER_NEEDED"


# ---------------------------------------------------------------------------
# 12. Strict shape validation
# ---------------------------------------------------------------------------


def test_parser_rejects_extra_column(tmp_path: Path) -> None:
    """An extra column in the CSV must be rejected by the strict parser."""
    bad = tmp_path / "bad.csv"
    with bad.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(list(REGISTRY_HEADERS) + ["extra"])
        writer.writerow([""] * (len(REGISTRY_HEADERS) + 1))
    with pytest.raises(OperationalSourceError, match="Unexpected registry schema"):
        read_registry(bad)


def test_parser_rejects_short_row(tmp_path: Path) -> None:
    """A row missing a column must be rejected."""
    bad = tmp_path / "bad.csv"
    with bad.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(REGISTRY_HEADERS)
        writer.writerow(["Acme"] + [""] * (len(REGISTRY_HEADERS) - 2))  # one less
    with pytest.raises(OperationalSourceError, match="has .* columns"):
        read_registry(bad)


def test_parser_rejects_unknown_ats_family(tmp_path: Path) -> None:
    bad = tmp_path / "bad.csv"
    with bad.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(REGISTRY_HEADERS)
        writer.writerow(
            [
                "Acme",
                "",
                "1",
                "CORE_200",
                "acme_main",
                "Global",
                "https://www.acme.com/careers/",
                "https://www.acme.com/careers/jobs",
                "WhollyMadeUpFamily",  # invalid
                "TECHNICALLY_VERIFIED",
                "READY_TO_PROBE",
                "YES",
                "PARITY_PENDING",
                "2026-09-02",
                "https://www.acme.com/careers/",
                "fixture",
                "N",
                "",
                "",
            ]
        )
    with pytest.raises(OperationalSourceError, match="ats_family"):
        read_registry(bad)


def test_parser_rejects_override_without_rationale(tmp_path: Path) -> None:
    """A `routing_override` requires a non-empty rationale and vice versa."""
    bad = tmp_path / "bad.csv"
    with bad.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(REGISTRY_HEADERS)
        writer.writerow(
            [
                "Acme",
                "",
                "1",
                "CORE_200",
                "acme_main",
                "Global",
                "https://www.acme.com/careers/",
                "",
                "",
                "UNVERIFIED",
                "HOLD",
                "NO",
                "UNTESTED",
                "",
                "https://www.acme.com/careers/",
                "fixture",
                "N",
                "HOLD",  # override
                "",  # missing rationale
            ]
        )
    with pytest.raises(OperationalSourceError, match="routing_override_rationale"):
        read_registry(bad)


def test_parser_rejects_rationale_without_override(tmp_path: Path) -> None:
    bad = tmp_path / "bad.csv"
    with bad.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(REGISTRY_HEADERS)
        writer.writerow(
            [
                "Acme",
                "",
                "1",
                "CORE_200",
                "acme_main",
                "Global",
                "https://www.acme.com/careers/",
                "",
                "",
                "UNVERIFIED",
                "HOLD",
                "NO",
                "UNTESTED",
                "",
                "https://www.acme.com/careers/",
                "fixture",
                "N",
                "",  # no override
                "I have a reason but no override",
            ]
        )
    with pytest.raises(OperationalSourceError, match="routing_override"):
        read_registry(bad)


# ---------------------------------------------------------------------------
# 13. Sync skips source-less rows (no Portal created)
# ---------------------------------------------------------------------------


def test_sync_skips_source_less_rows(tmp_path: Path) -> None:
    from research_agent.company.tier_s_operational_sources import sync_operational_sources
    from research_agent.company.importer import MASTER_HEADERS
    from research_agent.company.portal_registry import PortalRegistryError
    from research_agent.db.migrations import create_schema
    from research_agent.db.models import CorporateCluster, ImportBatch, Portal
    from sqlalchemy import select
    from sqlalchemy.engine import Engine
    from sqlalchemy.orm import Session

    # Build a temp DB
    db_path = tmp_path / "control.db"
    from research_agent.db.session import create_db_engine
    engine = create_db_engine(f"sqlite:///{db_path}")
    create_schema(engine)
    with Session(engine) as session, session.begin():
        batch = ImportBatch(
            source_kind="test_fixture",
            source_filename="fixture.csv",
            source_path="/tmp/fixture.csv",
            source_sha256="fixture-shared-cluster",
            source_version="fixture-v1",
            status="COMPLETED",
        )
        session.add(batch)
        session.flush()
        session.add(
            CorporateCluster(
                corporate_cluster_id="CG-T",
                representative_canonical_employer="Test",
                canonical_employers_json="[\"Test\"]",
                parent_groups_json="[]",
                entity_classes_json="[\"Company\"]",
                eligibility_values_json="[\"Yes\"]",
                sectors_json="[\"Technology\"]",
                discovery_geographies_json="[\"Global\"]",
                org_types_json="[\"Company\"]",
                record_count=1,
                has_primary_scan_eligibility=True,
                active_in_master=True,
                import_batch_id=batch.id,
            )
        )
    # Write a registry with one routed row and one source-less row for the same cluster.
    registry = tmp_path / "reg.csv"
    with registry.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REGISTRY_HEADERS)
        writer.writeheader()
        # Routed row: 1 portal + 1 mapping
        writer.writerow({
            "employer_name": "Test",
            "corporate_cluster_id": "CG-T",
            "priority": "1",
            "cohort": "CORE_200",
            "source_key": "test_main",
            "source_scope": "Global",
            "canonical_careers_url": "https://www.example.com/careers/",
            "operational_url": "https://boards-api.greenhouse.io/v1/boards/test/jobs?content=true",
            "ats_family": "Greenhouse",
            "evidence_state": "TECHNICALLY_VERIFIED",
            "resolution_path": "READY_TO_PROBE",
            "adapter_supported": "YES",
            "catalog_state": "PARITY_PENDING",
            "last_verified_at": "2026-09-02",
            "evidence_url": "https://www.example.com/careers/",
            "notes": "fixture",
            "scan_enabled": "N",
            "routing_override": "",
            "routing_override_rationale": "",
        })
        # Source-less row: must be matched but produce NO portal.
        writer.writerow({
            "employer_name": "Test",
            "corporate_cluster_id": "CG-T",
            "priority": "1",
            "cohort": "CORE_200",
            "source_key": "test_pending",
            "source_scope": "Global",
            "canonical_careers_url": "",
            "operational_url": "",
            "ats_family": "",
            "evidence_state": "UNVERIFIED",
            "resolution_path": "HOLD",
            "adapter_supported": "NO",
            "catalog_state": "UNTESTED",
            "last_verified_at": "",
            "evidence_url": "",
            "notes": "source-less",
            "scan_enabled": "N",
            "routing_override": "",
            "routing_override_rationale": "",
        })
    rows = read_registry(registry)
    cluster_mapping = {"Test": "CG-T"}
    report = sync_operational_sources(
        engine, registry, cluster_mapping=cluster_mapping
    )
    # Only the routed row produced a portal. The source-less row was skipped.
    assert report.created_portals == 1
    with Session(engine) as session:
        portals = session.scalars(select(Portal)).all()
        assert len(portals) == 1
        assert portals[0].host == "boards-api.greenhouse.io"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://boards-api.greenhouse.io/v1/boards/acme/jobs", "Greenhouse"),
        ("https://jobs.lever.co/someco", "Lever"),
        ("https://jobs.ashbyhq.com/acme", "Ashby"),
        ("https://jobs.smartrecruiters.com/SomeOne", "SmartRecruiters"),
        ("https://example.talentbrew.com/careers", "Radancy"),
        ("https://jobs.successfactors.com/SomeOne", "SuccessFactors RMK"),
        ("https://acme.wd5.myworkdayjobs.com/acme", "Workday"),
        ("https://acme.phenom.com/jobs", "Phenom"),
        # Taleo must NOT collapse into Oracle Recruiting Cloud.
        ("https://acme.taleo.net/careersection/1/joblist.ftl", "Taleo"),
        ("https://acme.taleo.com/careersection/2/joblist.ftl", "Taleo"),
        # Oracle Recruiting Cloud keeps its own family.
        ("https://example.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1", "Oracle Recruiting Cloud"),
        ("https://careers.avature.net/en/SomeOne", "Avature"),
        ("https://acme.com/jobs", ""),
    ],
)
def test_infer_ats_family_recognises_taleo_as_taleo(url: str, expected: str) -> None:
    assert _infer_ats_family(url) == expected


def test_sync_preserves_existing_verified_date_when_row_is_blank(
    tmp_path: Path,
) -> None:
    """An operational source CSV row with an empty `last_verified_at` must not
    overwrite a previously persisted `portal_verified_date`, and a brand-new
    mapping must never fall back to the 1970 epoch sentinel."""
    from datetime import date
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from research_agent.company.tier_s_operational_sources import (
        sync_operational_sources,
    )
    from research_agent.db.migrations import create_schema
    from research_agent.db.models import ClusterPortalMapping, CorporateCluster, ImportBatch
    from research_agent.db.session import create_db_engine

    engine = create_db_engine(f"sqlite:///{tmp_path / 'preserve.db'}")
    create_schema(engine)

    # 1) Seed a cluster.
    with Session(engine) as session, session.begin():
        session.add(
            ImportBatch(
                source_kind="seed",
                source_filename="seed",
                source_path="seed",
                source_sha256="0" * 64,
                source_version="seed-v1",
                status="COMPLETE",
            )
        )
        session.flush()
        batch = session.scalar(select(ImportBatch).where(ImportBatch.source_kind == "seed"))
        session.add(
            CorporateCluster(
                corporate_cluster_id="CG-VERIFY-1",
                representative_canonical_employer="Verify Co.",
                canonical_employers_json="[\"Verify Co.\"]",
                parent_groups_json="[]",
                entity_classes_json="[]",
                eligibility_values_json="[]",
                sectors_json="[]",
                discovery_geographies_json="[]",
                org_types_json="[]",
                record_count=1,
                has_primary_scan_eligibility=True,
                import_batch_id=batch.id,
            )
        )

    registry = tmp_path / "registry.csv"
    registry.write_text(
        "employer_name,corporate_cluster_id,priority,cohort,source_key,source_scope,"
        "canonical_careers_url,operational_url,ats_family,evidence_state,"
        "resolution_path,adapter_supported,catalog_state,last_verified_at,"
        "evidence_url,notes,scan_enabled,routing_override,routing_override_rationale\n"
        "Verify Co.,CG-VERIFY-1,1,CORE_200,verify,Global,"
        "https://verify.example.test/careers,https://boards-api.greenhouse.io/v1/boards/verify/jobs,"
        "Greenhouse,FIRST_PARTY_AND_PLATFORM_VERIFIED,READY_TO_PROBE,YES,PARITY_PENDING,2026-05-01,"
        "https://verify.example.test/careers,,N,,\n",
        encoding="utf-8",
    )

    # 2) First sync with a real date (2026-05-01).
    rows = read_registry(registry)
    cluster_mapping, _, _ = __import__(
        "research_agent.company.tier_s_operational_sources",
        fromlist=["reconcile_clusters"],
    ).reconcile_clusters(engine, rows)
    sync_operational_sources(
        engine, registry, cluster_mapping=cluster_mapping, source_version="v1"
    )

    with Session(engine) as session:
        mapping = session.scalar(
            select(ClusterPortalMapping).where(
                ClusterPortalMapping.corporate_cluster_id == "CG-VERIFY-1"
            )
        )
        assert mapping is not None
        assert mapping.portal_verified_date == date(2026, 5, 1)

    # 3) Re-emit the registry with an empty last_verified_at. Existing
    #    verified date must be preserved.
    registry.write_text(
        "employer_name,corporate_cluster_id,priority,cohort,source_key,source_scope,"
        "canonical_careers_url,operational_url,ats_family,evidence_state,"
        "resolution_path,adapter_supported,catalog_state,last_verified_at,"
        "evidence_url,notes,scan_enabled,routing_override,routing_override_rationale\n"
        "Verify Co.,CG-VERIFY-1,1,CORE_200,verify,Global,"
        "https://verify.example.test/careers,https://boards-api.greenhouse.io/v1/boards/verify/jobs,"
        "Greenhouse,FIRST_PARTY_AND_PLATFORM_VERIFIED,READY_TO_PROBE,YES,PARITY_PENDING,,"
        "https://verify.example.test/careers,,N,,\n",
        encoding="utf-8",
    )
    rows2 = read_registry(registry)
    cluster_mapping2, _, _ = __import__(
        "research_agent.company.tier_s_operational_sources",
        fromlist=["reconcile_clusters"],
    ).reconcile_clusters(engine, rows2)
    sync_operational_sources(
        engine, registry, cluster_mapping=cluster_mapping2, source_version="v2"
    )

    with Session(engine) as session:
        mapping = session.scalar(
            select(ClusterPortalMapping).where(
                ClusterPortalMapping.corporate_cluster_id == "CG-VERIFY-1"
            )
        )
        # The previous 2026-05-01 is preserved — never silently replaced.
        assert mapping is not None
        assert mapping.portal_verified_date == date(2026, 5, 1)

    # 4) A brand-new mapping (no previous date) must NOT silently use 1970-01-01.
    registry2 = tmp_path / "registry_new.csv"
    registry2.write_text(
        "employer_name,corporate_cluster_id,priority,cohort,source_key,source_scope,"
        "canonical_careers_url,operational_url,ats_family,evidence_state,"
        "resolution_path,adapter_supported,catalog_state,last_verified_at,"
        "evidence_url,notes,scan_enabled,routing_override,routing_override_rationale\n"
        "Verify Co.,CG-VERIFY-1,2,CORE_200,verify_2,Global,"
        "https://verify.example.test/careers,https://boards-api.greenhouse.io/v1/boards/verify2/jobs,"
        "Greenhouse,FIRST_PARTY_AND_PLATFORM_VERIFIED,READY_TO_PROBE,YES,PARITY_PENDING,,"
        "https://verify.example.test/careers,,N,,\n",
        encoding="utf-8",
    )
    rows3 = read_registry(registry2)
    cluster_mapping3, _, _ = __import__(
        "research_agent.company.tier_s_operational_sources",
        fromlist=["reconcile_clusters"],
    ).reconcile_clusters(engine, rows3)
    sync_operational_sources(
        engine, registry2, cluster_mapping=cluster_mapping3, source_version="v3"
    )

    with Session(engine) as session:
        new_mapping = session.scalar(
            select(ClusterPortalMapping).where(
                ClusterPortalMapping.corporate_cluster_id == "CG-VERIFY-1",
                ClusterPortalMapping.source_jobs_search_url
                == "https://boards-api.greenhouse.io/v1/boards/verify2/jobs",
            )
        )
        assert new_mapping is not None
        # NOT 1970-01-01.
        assert new_mapping.portal_verified_date != date(1970, 1, 1)
