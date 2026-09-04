"""Operational Source Control Plane — translate Tier-S research ledger into runtime state.

This module is intentionally offline, deterministic and additive. It reads a
structured CSV registry (not the Markdown research ledger) and produces:

  * a corporate-cluster reconciliation report;
  * an idempotent sync of `Portal` + `ClusterPortalMapping` rows;
  * five resolution queues and a machine-readable summary.

The mapping file `TIER_S_ATS_MAPPING.md` is the audit trail. This module never
parses it directly. The CSV is the only runtime input.

Hard invariants:

  * no HTTP is performed here;
  * no LLM is invoked here;
  * no `SourceJob` or `JobAiAnalysis` row is mutated;
  * lifecycle and closure state are never advanced;
  * existing operational sources are never disabled or deleted by a sync;
  * the same operational URL deduplicates against existing `Portal` rows.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_agent.company.importer import file_sha256
from research_agent.company.portal_registry import normalize_jobs_url
from research_agent.db.migrations import create_schema
from research_agent.db.models import (
    ClusterPortalMapping,
    CorporateCluster,
    ImportBatch,
    Portal,
    utc_now,
)


# ---------------------------------------------------------------------------
# Public schema and routing vocabulary
# ---------------------------------------------------------------------------


# Columns we publish and consume. Order matters (CSV header order).
REGISTRY_HEADERS: tuple[str, ...] = (
    "employer_name",
    "corporate_cluster_id",
    "priority",
    "cohort",
    "source_key",
    "source_scope",
    "canonical_careers_url",
    "operational_url",
    "ats_family",
    "evidence_state",
    "resolution_path",
    "adapter_supported",
    "catalog_state",
    "last_verified_at",
    "evidence_url",
    "notes",
    "scan_enabled",
    "routing_override",
    "routing_override_rationale",
)

VALID_COHORTS: tuple[str, ...] = ("CORE_200", "CORE_EXTENSION")
VALID_RESOLUTION_PATHS: tuple[str, ...] = (
    "READY_TO_PROBE",
    "FINGERPRINT_REQUIRED",
    "ADAPTER_NEEDED",
    "RESOLVER_LIGHT",
    "HOLD",
)
VALID_CATALOG_STATES: tuple[str, ...] = (
    "UNTESTED",
    "PARITY_PENDING",
    "VERIFIED",
    "PARTIAL",
    "FIX_REQUIRED",
)
VALID_EVIDENCE_STATES: tuple[str, ...] = (
    "FIRST_PARTY_VERIFIED",
    "TECHNICALLY_VERIFIED",
    "FIRST_PARTY_AND_PLATFORM_VERIFIED",
    "OPERATIONAL_PLATFORM_VERIFIED",
    "GREENHOUSE_OPERATIONAL_PLATFORM_VERIFIED",
    "FIRST_PARTY_VERIFIED_PLATFORM",
    "TECHNICALLY_VERIFIED_PLATFORM",
    "PROBABLE",
    "UNVERIFIED",
)

# Adapters the V24 ZIP actually registers. Anything not here is "ADAPTER_NEEDED".
SUPPORTED_ADAPTERS: frozenset[str] = frozenset(
    {
        "Greenhouse",
        "Lever",
        "Ashby",
        "SmartRecruiters",
        "Radancy",
        "SuccessFactors RMK",
        "Workday",
        "Phenom",
        "Oracle Recruiting Cloud",
        "Avature",
        "Custom Google RPC",
        # GenericOfficialHtml is a parser fallback, not a structured adapter
        # and is treated as "adapter supported" for routing only when the
        # operational URL is itself a first-party HTML catalog. Otherwise
        # the source is held / fingerprint-required.
    }
)

# ATS families that exist in the real world but are NOT supported by the V24
# ZIP. A row in this set triggers `ADAPTER_NEEDED` if evidence is current
# enough. `Taleo` is its own family and must NEVER be merged with
# `Oracle Recruiting Cloud` even though both belong to Oracle.
UNSUPPORTED_REUSABLE_FAMILIES: frozenset[str] = frozenset(
    {
        "Taleo",
        "Eightfold",
        "BrassRing",
        "Teamtailor",
        "Pereless",
    }
)

# Adapters that have an implementation in V24 but are NOT the right family
# to claim for a row. These exist so the validator can refuse a `Taleo` row
# mislabelled as `Oracle Recruiting Cloud`.
DISTINCT_FAMILIES: frozenset[str] = (
    SUPPORTED_ADAPTERS | UNSUPPORTED_REUSABLE_FAMILIES
)


class OperationalSourceError(ValueError):
    """Raised for any structural or validation problem in the registry."""


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OperationalSourceRow:
    employer_name: str
    corporate_cluster_id: str  # "" if unmatched/ambiguous
    priority: str
    cohort: str
    source_key: str
    source_scope: str
    canonical_careers_url: str
    operational_url: str  # may be empty when source is unresolved
    ats_family: str  # may be empty when source is unresolved
    evidence_state: str
    resolution_path: str
    adapter_supported: str  # YES / NO / UNKNOWN
    catalog_state: str
    last_verified_at: str  # may be empty when unknown
    evidence_url: str
    notes: str
    scan_enabled: bool
    routing_override: str  # may be empty: explicit override of derived routing
    routing_override_rationale: str  # must be non-empty if override is set


@dataclass(frozen=True)
class ReconcileCandidate:
    corporate_cluster_id: str
    representative_canonical_employer: str
    matched_name: str
    matched_name_source: str  # master / verified_alias / parent_group


@dataclass(frozen=True)
class SyncReport:
    import_batch_id: int
    source_sha256: str
    source_path: str
    already_applied: bool
    matched_employers: tuple[str, ...]
    unmatched_employers: tuple[str, ...]
    matched_rows: int
    total_rows: int
    multi_source_employers: tuple[str, ...]
    created_portals: int
    reused_portals: int
    created_mappings: int
    updated_mappings: int
    action_counts: dict[str, int]


# ---------------------------------------------------------------------------
# CSV I/O
# ---------------------------------------------------------------------------


def read_registry(path: Path) -> list[OperationalSourceRow]:
    """Read and validate the structured operational source registry CSV.

    Strict shape validation:

      * the header row must be exactly the columns declared in
        `REGISTRY_HEADERS`, in that order;
      * every data row must have exactly that column count (no extra columns,
        no missing columns, no malformed quoting);
      * `operational_url` may be empty (unresolved sources);
      * `last_verified_at` may be empty (unknown date);
      * `ats_family` must be empty, supported, or an unsupported reusable
        family (`Taleo` is a distinct family and must never be merged with
        `Oracle Recruiting Cloud`);
      * `routing_override` requires a non-empty rationale, and vice versa.
    """

    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise OperationalSourceError(f"Registry file not found: {resolved}")
    with resolved.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            raise OperationalSourceError("Registry is empty")
        actual = tuple(header)
        if actual != REGISTRY_HEADERS:
            raise OperationalSourceError(
                f"Unexpected registry schema. Expected {list(REGISTRY_HEADERS)}, "
                f"got {list(actual)}"
            )
        raw_rows = list(reader)
    if not raw_rows:
        raise OperationalSourceError("Registry is empty")
    parsed: list[OperationalSourceRow] = []
    for index, raw in enumerate(raw_rows, start=2):
        if len(raw) != len(REGISTRY_HEADERS):
            raise OperationalSourceError(
                f"Row {index} has {len(raw)} columns, expected {len(REGISTRY_HEADERS)}; "
                "check for unquoted commas or stray delimiters"
            )
        record = {header: (raw[i] if i < len(raw) else "").strip() for i, header in enumerate(REGISTRY_HEADERS)}
        parsed.append(_parse_row(record, row=index))
    # Cross-row invariants: aggregate over the full registry.
    problems = validate_registry_invariants(parsed)
    if problems:
        sample = problems[:10]
        raise OperationalSourceError(
            f"Registry failed cross-row invariants: {len(problems)} problem(s). "
            f"First {len(sample)}: {sample}"
        )
    return parsed


def _parse_row(raw: dict[str, str], *, row: int) -> OperationalSourceRow:
    employer = (raw["employer_name"] or "").strip()
    if not employer:
        raise OperationalSourceError(f"Row {row} is missing employer_name")
    cohort = (raw["cohort"] or "").strip()
    if cohort not in VALID_COHORTS:
        raise OperationalSourceError(
            f"Row {row} has invalid cohort {cohort!r}; expected one of {list(VALID_COHORTS)}"
        )
    routing_override = (raw.get("routing_override") or "").strip().upper()
    if routing_override and routing_override not in VALID_RESOLUTION_PATHS:
        raise OperationalSourceError(
            f"Row {row} has invalid routing_override {routing_override!r}; "
            f"expected one of {list(VALID_RESOLUTION_PATHS)} or empty"
        )
    override_rationale = (raw.get("routing_override_rationale") or "").strip()
    if bool(routing_override) != bool(override_rationale):
        raise OperationalSourceError(
            f"Row {row} has routing_override={routing_override!r} but "
            f"routing_override_rationale={override_rationale!r}; both must be present or both empty"
        )
    resolution = (raw["resolution_path"] or "").strip()
    if resolution not in VALID_RESOLUTION_PATHS:
        raise OperationalSourceError(
            f"Row {row} has invalid resolution_path {resolution!r}; "
            f"expected one of {list(VALID_RESOLUTION_PATHS)}"
        )
    if routing_override and routing_override != resolution:
        # If an override is supplied, resolution_path must equal it.
        raise OperationalSourceError(
            f"Row {row} has resolution_path={resolution!r} but "
            f"routing_override={routing_override!r}; the two must agree when an override is set"
        )
    catalog = (raw["catalog_state"] or "").strip()
    if catalog not in VALID_CATALOG_STATES:
        raise OperationalSourceError(
            f"Row {row} has invalid catalog_state {catalog!r}; "
            f"expected one of {list(VALID_CATALOG_STATES)}"
        )
    evidence = (raw["evidence_state"] or "").strip()
    if evidence not in VALID_EVIDENCE_STATES:
        raise OperationalSourceError(
            f"Row {row} has invalid evidence_state {evidence!r}; "
            f"expected one of {list(VALID_EVIDENCE_STATES)}"
        )
    scan_enabled = (raw["scan_enabled"] or "").strip().upper() in {"Y", "YES", "TRUE", "1"}
    cluster_id = (raw["corporate_cluster_id"] or "").strip()
    canonical = (raw["canonical_careers_url"] or "").strip()
    operational = (raw["operational_url"] or "").strip()
    # `canonical_careers_url` may be empty ONLY when the operational URL
    # is also empty AND the routing is HOLD — the registry's record that
    # the cluster is in CORE_200 but no operational source is known.
    if not canonical and operational:
        raise OperationalSourceError(
            f"Row {row} is missing canonical_careers_url but has an operational_url; "
            "the canonical surface should be filled in whenever an operational source is known"
        )
    if canonical:
        _validate_url(canonical, row=row, field="canonical_careers_url")
    if operational:
        _validate_url(operational, row=row, field="operational_url")
    last_verified = (raw["last_verified_at"] or "").strip()
    if last_verified:
        try:
            date.fromisoformat(last_verified)
        except ValueError as exc:
            raise OperationalSourceError(
                f"Row {row} has invalid last_verified_at {last_verified!r}: {exc}"
            ) from exc
    # NOTE: we deliberately keep `last_verified` blank if the row did not
    # supply one; we do not invent "today" as the date.
    adapter_supported = (raw["adapter_supported"] or "NO").strip().upper()
    if adapter_supported not in {"YES", "NO", "UNKNOWN"}:
        raise OperationalSourceError(
            f"Row {row} has invalid adapter_supported {adapter_supported!r}"
        )
    ats_family = (raw["ats_family"] or "").strip()
    if ats_family and ats_family not in DISTINCT_FAMILIES:
        # Taleo is its own family; reject rows that pretend to be a
        # supported family while not being in the supported set.
        raise OperationalSourceError(
            f"Row {row} has ats_family={ats_family!r} which is not a known family; "
            f"expected one of {sorted(DISTINCT_FAMILIES)} or empty"
        )
    return OperationalSourceRow(
        employer_name=employer,
        corporate_cluster_id=cluster_id,
        priority=(raw["priority"] or "").strip(),
        cohort=cohort,
        source_key=(raw["source_key"] or "").strip() or f"{employer.lower()}_auto",
        source_scope=(raw["source_scope"] or "Global").strip(),
        canonical_careers_url=canonical,
        operational_url=operational,
        ats_family=ats_family,
        evidence_state=evidence,
        resolution_path=resolution,
        adapter_supported=adapter_supported,
        catalog_state=catalog,
        last_verified_at=last_verified,
        evidence_url=(raw["evidence_url"] or "").strip(),
        notes=(raw["notes"] or "").strip(),
        scan_enabled=scan_enabled,
        routing_override=routing_override,
        routing_override_rationale=override_rationale,
    )


def _validate_url(value: str, *, row: int, field: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise OperationalSourceError(f"Row {row} has invalid {field}: {value!r}")


# ---------------------------------------------------------------------------
# Routing derivation + cross-row invariants
# ---------------------------------------------------------------------------


# Evidence classes that the audit-v2 method considers automation-grade.
AUTOMATION_GRADE_EVIDENCE: frozenset[str] = frozenset(
    {
        "FIRST_PARTY_VERIFIED",
        "TECHNICALLY_VERIFIED",
        "FIRST_PARTY_AND_PLATFORM_VERIFIED",
        "OPERATIONAL_PLATFORM_VERIFIED",
        "GREENHOUSE_OPERATIONAL_PLATFORM_VERIFIED",
        "FIRST_PARTY_VERIFIED_PLATFORM",
        "TECHNICALLY_VERIFIED_PLATFORM",
    }
)


def derive_routing(
    *,
    evidence_state: str,
    ats_family: str,
    adapter_supported: str,
    operational_url: str,
) -> str:
    """Derive the routing queue from evidence + platform + adapter + URL.

    The rule (V25.1):

      * no operational URL + UNVERIFIED/PROBABLE   -> HOLD
      * no operational URL + automation-grade      -> HOLD (still source-less)
      * operational URL + automation-grade +
        supported adapter + ats_family in supported set   -> READY_TO_PROBE
      * operational URL + automation-grade +
        ats_family in unsupported reusable families       -> ADAPTER_NEEDED
      * operational URL + automation-grade +
        ats_family unknown                                -> ADAPTER_NEEDED
      * operational URL + PROBABLE                         -> FINGERPRINT_REQUIRED
      * operational URL + UNVERIFIED + known first-party   -> RESOLVER_LIGHT
      * operational URL + UNVERIFIED otherwise              -> HOLD

    `catalog_state` is intentionally NOT part of routing; platform
    verification != catalog verification. `catalog_state=VERIFIED` is
    reserved for the post-probe parity check, not for routing.
    """

    has_url = bool(operational_url.strip())
    if not has_url:
        return "HOLD"
    if evidence_state in AUTOMATION_GRADE_EVIDENCE:
        if ats_family in SUPPORTED_ADAPTERS and adapter_supported.upper() == "YES":
            return "READY_TO_PROBE"
        if ats_family in UNSUPPORTED_REUSABLE_FAMILIES:
            return "ADAPTER_NEEDED"
        if not ats_family:
            return "ADAPTER_NEEDED"
        # ats_family in DISTINCT_FAMILIES but not supported AND not reusable
        # (e.g. an old custom backend). Treat as ADAPTER_NEEDED so the
        # next milestone knows it is not yet ready.
        return "ADAPTER_NEEDED"
    if evidence_state == "PROBABLE":
        return "FINGERPRINT_REQUIRED"
    # UNVERIFIED: at this point we know the URL but not the backend.
    if evidence_state == "UNVERIFIED":
        return "RESOLVER_LIGHT"
    # Unknown evidence state — already rejected by `_parse_row`, but keep
    # an explicit branch for defence in depth.
    return "HOLD"


def validate_routing(row: OperationalSourceRow) -> list[str]:
    """Return a list of routing contradictions the registry rejects.

    Empty list == row is internally consistent.

    An explicit `routing_override` requires a non-empty rationale; the
    override may differ from the derived routing when the human decision
    reflects project priorities (e.g. back-burner HOLD for an unresolved
    custom backend) that the derivation rule cannot express.
    """

    problems: list[str] = []
    expected = derive_routing(
        evidence_state=row.evidence_state,
        ats_family=row.ats_family,
        adapter_supported=row.adapter_supported,
        operational_url=row.operational_url,
    )
    if expected != row.resolution_path:
        if row.routing_override and row.routing_override == row.resolution_path:
            # Human override is allowed: it must have a rationale (we
            # already enforce that during parse), and it must be one of
            # the recognised queues. We do not second-guess the override
            # beyond that.
            pass
        else:
            problems.append(
                f"resolution_path={row.resolution_path!r} does not match derived "
                f"routing={expected!r} from evidence={row.evidence_state!r} + "
                f"adapter={row.ats_family!r} supported={row.adapter_supported!r} + url={'set' if row.operational_url else 'empty'}"
            )
    if not row.operational_url and row.resolution_path != "HOLD":
        problems.append(
            f"row has no operational_url but routing={row.resolution_path!r}; "
            "only HOLD is valid for source-less rows"
        )
    if row.ats_family == "Taleo" and "Oracle Recruiting Cloud" in (row.notes or ""):
        # The forbidden pattern: do not pretend Taleo is ORC.
        problems.append(
            "Taleo is its own ATS family; do not label it as Oracle Recruiting Cloud"
        )
    return problems


def validate_registry_invariants(rows: list[OperationalSourceRow]) -> list[str]:
    """Cross-row invariants enforced at parse time."""

    problems: list[str] = []
    # Multi-source uniqueness: for the same (employer, source_key) the row
    # must be unique. Multi-source is allowed (different source_keys), but
    # we still require deterministic, stable source keys.
    keys: set[tuple[str, str]] = set()
    for r in rows:
        key = (r.employer_name, r.source_key)
        if key in keys:
            problems.append(
                f"duplicate (employer_name={r.employer_name!r}, source_key={r.source_key!r})"
            )
        keys.add(key)
    # Per-employer routing consistency: all rows for the same employer
    # with operational sources should agree on the routing decision family.
    by_employer: dict[str, list[OperationalSourceRow]] = defaultdict(list)
    for r in rows:
        by_employer[r.employer_name].append(r)
    for employer, employer_rows in by_employer.items():
        with_url = [r for r in employer_rows if r.operational_url]
        if not with_url:
            continue
        # All routed rows for the same employer should land in the same
        # coarse bucket: PROBE, ADAPTER_NEEDED, or RESOLVER_LIGHT. Multiple
        # READY_TO_PROBE rows for the same employer is fine; HOLD is fine
        # for a source-less row alongside PROBE rows.
        buckets = {derive_routing(
            evidence_state=r.evidence_state,
            ats_family=r.ats_family,
            adapter_supported=r.adapter_supported,
            operational_url=r.operational_url,
        ) for r in with_url}
        if "READY_TO_PROBE" in buckets and "FINGERPRINT_REQUIRED" in buckets:
            problems.append(
                f"employer {employer!r} has rows in both READY_TO_PROBE and "
                "FINGERPRINT_REQUIRED; reconcile before merging registries"
            )
        if "READY_TO_PROBE" in buckets and "ADAPTER_NEEDED" in buckets:
            problems.append(
                f"employer {employer!r} has rows in both READY_TO_PROBE and "
                "ADAPTER_NEEDED; reconcile before merging registries"
            )
    # Per-employer routing contradictions on the row itself.
    for r in rows:
        problems.extend(f"{r.employer_name} / {r.source_key}: {p}" for p in validate_routing(r))
    return problems


# ---------------------------------------------------------------------------
# CorporateCluster reconciliation
# ---------------------------------------------------------------------------


def reconcile_clusters(
    engine: Engine,
    rows: list[OperationalSourceRow],
) -> tuple[dict[str, str], list[dict[str, str]], list[ReconcileCandidate]]:
    """Match each registry row to a `CorporateCluster` deterministically.

    The mapping function:

      1. honours an explicit `corporate_cluster_id` when present and the
         cluster exists in the database;
      2. otherwise matches `employer_name` against the cluster's
         `representative_canonical_employer` or any name in
         `canonical_employers_json` / `parent_groups_json` (case-folded exact
         match);
      3. honours a `VERIFIED` `CompanyAlias` for the same normalized form;
      4. never falls back to fuzzy auto-write.

    Returns:

      * `mapping`: employer_name -> corporate_cluster_id ("" if unmatched);
      * `unmatched`: rows in the form consumed by
        `output/mapping/tier_s_operational_sources_unmatched.csv`;
      * `candidates`: structured explanations of how each match happened.
    """

    create_schema(engine)
    with Session(engine) as session:
        clusters = session.scalars(select(CorporateCluster)).all()
        verified_aliases = session.scalars(
            select(__import__("research_agent.db.models", fromlist=["CompanyAlias"]).CompanyAlias).where(
                __import__("research_agent.db.models", fromlist=["CompanyAlias"]).CompanyAlias.status == "VERIFIED"
            )
        ).all()

    cluster_by_id: dict[str, CorporateCluster] = {
        cluster.corporate_cluster_id: cluster for cluster in clusters
    }
    names_by_cluster: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for cluster in clusters:
        rep = (cluster.representative_canonical_employer or "").strip()
        if rep:
            names_by_cluster[cluster.corporate_cluster_id].append((rep.casefold(), "master"))
        try:
            for name in json.loads(cluster.canonical_employers_json or "[]"):
                if name:
                    names_by_cluster[cluster.corporate_cluster_id].append((name.casefold(), "master"))
        except json.JSONDecodeError:
            pass
        try:
            for name in json.loads(cluster.parent_groups_json or "[]"):
                if name:
                    names_by_cluster[cluster.corporate_cluster_id].append((name.casefold(), "parent_group"))
        except json.JSONDecodeError:
            pass
    alias_to_cluster: dict[str, str] = {}
    for alias in verified_aliases:
        normalized = (alias.normalized_alias or "").strip().casefold()
        if normalized and alias.corporate_cluster_id in cluster_by_id:
            alias_to_cluster[normalized] = alias.corporate_cluster_id

    mapping: dict[str, str] = {}
    unmatched: list[dict[str, str]] = []
    candidates: list[ReconcileCandidate] = []
    seen_employers: set[str] = set()

    for row in rows:
        employer = row.employer_name
        if employer in seen_employers:
            continue
        seen_employers.add(employer)
        target_id = ""
        reason = ""
        possible = []
        # 1. explicit cluster id, only if the cluster actually exists.
        if row.corporate_cluster_id:
            if row.corporate_cluster_id in cluster_by_id:
                target_id = row.corporate_cluster_id
                cluster = cluster_by_id[row.corporate_cluster_id]
                candidates.append(
                    ReconcileCandidate(
                        corporate_cluster_id=cluster.corporate_cluster_id,
                        representative_canonical_employer=cluster.representative_canonical_employer,
                        matched_name=cluster.representative_canonical_employer,
                        matched_name_source="explicit_cluster_id",
                    )
                )
            else:
                reason = f"explicit cluster_id {row.corporate_cluster_id!r} not in database"
                possible = []
        # 2. alias exact match.
        if not target_id and employer.casefold() in alias_to_cluster:
            target_id = alias_to_cluster[employer.casefold()]
            candidates.append(
                ReconcileCandidate(
                    corporate_cluster_id=target_id,
                    representative_canonical_employer=cluster_by_id[target_id].representative_canonical_employer,
                    matched_name=employer,
                    matched_name_source="verified_alias",
                )
            )
        # 3. exact casefold match against cluster names (master/parent_group).
        if not target_id:
            for cluster_id, names in names_by_cluster.items():
                for name, source in names:
                    if name == employer.casefold():
                        target_id = cluster_id
                        candidates.append(
                            ReconcileCandidate(
                                corporate_cluster_id=cluster_id,
                                representative_canonical_employer=cluster_by_id[cluster_id].representative_canonical_employer,
                                matched_name=employer,
                                matched_name_source=source,
                            )
                        )
                        break
                if target_id:
                    break
        # 4. build possible candidates listing for unmatched rows.
        if not target_id and not reason:
            reason = "no deterministic match: not a representative / canonical / parent / VERIFIED alias"
            for cluster_id, names in sorted(names_by_cluster.items()):
                for name, source in names:
                    if name and name in employer.casefold():
                        possible.append(
                            f"{cluster_by_id[cluster_id].representative_canonical_employer}"
                            f" ({cluster_id}, {source})"
                        )
        if not target_id:
            unmatched.append(
                {
                    "employer": employer,
                    "reason": reason or "no deterministic match",
                    "possible_candidates": "; ".join(possible[:5]),
                    "manual_review_required": "Y",
                }
            )
        mapping[employer] = target_id
    return mapping, unmatched, candidates


# ---------------------------------------------------------------------------
# Dry-run vs real sync
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DryRunResult:
    matched_employers: tuple[str, ...]
    unmatched_employers: tuple[str, ...]
    source_less_employers: tuple[str, ...]
    would_create_portals: int
    would_reuse_portals: int
    would_create_mappings: int
    would_update_mappings: int
    multi_source_employers: tuple[str, ...]
    total_rows: int


def dry_run_sync(
    engine: Engine,
    rows: list[OperationalSourceRow],
    cluster_mapping: dict[str, str],
) -> DryRunResult:
    """Compute the change set that `sync_operational_sources` would apply.

    Source-less rows (no operational_url) never produce a Portal. The dry
    run still counts them as matched when the cluster exists, so the
    coverage report is correct; only the portal/mapping counters skip
    them.
    """

    create_schema(engine)
    matched: list[str] = []
    unmatched: list[str] = []
    matched_rows = 0
    source_less_employers: set[str] = set()
    per_employer_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        cluster_id = cluster_mapping.get(row.employer_name, "")
        if not cluster_id:
            unmatched.append(row.employer_name)
            continue
        matched.append(row.employer_name)
        matched_rows += 1
        if not row.operational_url:
            source_less_employers.add(row.employer_name)
            continue
        per_employer_counts[row.employer_name] += 1
    multi_source = sorted(
        employer for employer, count in per_employer_counts.items() if count > 1
    )

    create_portals = 0
    reuse_portals = 0
    create_mappings = 0
    update_mappings = 0
    if matched_rows:
        existing_portals, existing_mappings = _load_existing_state(engine)
        for row in rows:
            cluster_id = cluster_mapping.get(row.employer_name, "")
            if not cluster_id or not row.operational_url:
                continue
            try:
                normalized = normalize_jobs_url(row.operational_url)
            except Exception:
                continue
            if normalized in existing_portals:
                reuse_portals += 1
            else:
                create_portals += 1
            key = (cluster_id, normalized)
            if key in existing_mappings:
                update_mappings += 1
            else:
                create_mappings += 1
    return DryRunResult(
        matched_employers=tuple(sorted(set(matched))),
        unmatched_employers=tuple(sorted(set(unmatched))),
        source_less_employers=tuple(sorted(source_less_employers)),
        would_create_portals=create_portals,
        would_reuse_portals=reuse_portals,
        would_create_mappings=create_mappings,
        would_update_mappings=update_mappings,
        multi_source_employers=tuple(multi_source),
        total_rows=len(rows),
    )


def sync_operational_sources(
    engine: Engine,
    path: Path,
    *,
    cluster_mapping: dict[str, str],
    source_version: str = "tier_s_v1",
) -> SyncReport:
    """Idempotent additive sync from registry CSV into Portal / ClusterPortalMapping.

    The sync:

      * never deletes or disables existing operational sources;
      * dedupes by `normalized_jobs_url` against existing `Portal` rows;
      * creates a new `ClusterPortalMapping` per (cluster, operational source)
        so a single cluster can hold many operational sources;
      * does not touch `SourceJob`, `JobAiAnalysis` or lifecycle state;
      * records an `ImportBatch` with `source_kind="tier_s_operational_sources"`
        and is fully idempotent on SHA-256.
    """

    resolved = path.expanduser().resolve()
    rows = read_registry(resolved)
    source_sha = file_sha256(resolved)
    create_schema(engine)
    with Session(engine) as session, session.begin():
        existing = session.scalar(
            select(ImportBatch).where(ImportBatch.source_sha256 == source_sha)
        )
        if existing is not None:
            if (
                existing.source_kind != "tier_s_operational_sources"
                or existing.status != "COMPLETED"
            ):
                raise OperationalSourceError(
                    f"Checksum belongs to incompatible import batch {existing.id}"
                )
            evidence = json.loads(existing.validation_json or "{}")
            return SyncReport(
                import_batch_id=existing.id,
                source_sha256=source_sha,
                source_path=str(resolved),
                already_applied=True,
                matched_employers=tuple(evidence.get("matched_employers", [])),
                unmatched_employers=tuple(evidence.get("unmatched_employers", [])),
                matched_rows=int(evidence.get("matched_rows", 0)),
                total_rows=int(evidence.get("total_rows", 0)),
                multi_source_employers=tuple(evidence.get("multi_source_employers", [])),
                created_portals=int(evidence.get("created_portals", 0)),
                reused_portals=int(evidence.get("reused_portals", 0)),
                created_mappings=int(evidence.get("created_mappings", 0)),
                updated_mappings=int(evidence.get("updated_mappings", 0)),
                action_counts=dict(evidence.get("action_counts", {})),
            )
        before = _database_metrics(session)
        batch = ImportBatch(
            source_kind="tier_s_operational_sources",
            source_filename=resolved.name,
            source_path=str(resolved),
            source_sha256=source_sha,
            source_version=source_version,
            status="RUNNING",
        )
        session.add(batch)
        session.flush()

        action_counts: Counter[str] = Counter()
        created_portals = 0
        reused_portals = 0
        created_mappings = 0
        updated_mappings = 0
        matched_employers: set[str] = set()
        unmatched_employers: set[str] = set()
        per_employer_count: dict[str, int] = defaultdict(int)
        existing_portal_by_url: dict[str, Portal] = {
            portal.normalized_jobs_url: portal
            for portal in session.scalars(select(Portal)).all()
        }
        existing_mappings_by_key: dict[tuple[str, str], ClusterPortalMapping] = {
            (mapping.corporate_cluster_id, mapping.portal.normalized_jobs_url): mapping
            for mapping in session.scalars(
                select(ClusterPortalMapping).join(Portal)
            ).all()
        }

        for row in rows:
            cluster_id = cluster_mapping.get(row.employer_name, "")
            if not cluster_id:
                unmatched_employers.add(row.employer_name)
                action_counts["skipped_unmatched"] += 1
                continue
            matched_employers.add(row.employer_name)
            # Source-less rows (no operational_url) are matched but do NOT
            # create or update any Portal / ClusterPortalMapping. They are
            # the registry's record that the cluster exists in the curated
            # CORE_200 and the routing is HOLD until an operational source
            # is identified. The routing invariants guarantee this branch
            # is the only one reachable for source-less rows.
            if not row.operational_url:
                action_counts["skipped_source_less"] += 1
                continue
            per_employer_count[row.employer_name] += 1
            try:
                normalized = normalize_jobs_url(row.operational_url)
            except Exception as exc:
                raise OperationalSourceError(
                    f"Cannot normalize operational URL for {row.employer_name} "
                    f"({row.source_key}): {exc}"
                ) from exc
            portal = existing_portal_by_url.get(normalized)
            if portal is None:
                portal = _create_portal(session, batch.id, normalized, row)
                existing_portal_by_url[normalized] = portal
                created_portals += 1
                action_counts["create_portal"] += 1
            else:
                reused_portals += 1
                action_counts["reuse_portal"] += 1
            key = (cluster_id, normalized)
            mapping = existing_mappings_by_key.get(key)
            verified_date = (
                date.fromisoformat(row.last_verified_at) if row.last_verified_at else None
            )
            if mapping is None:
                mapping = ClusterPortalMapping(
                    corporate_cluster_id=cluster_id,
                    portal_id=portal.id,
                    resolved_corporate_website=urlsplitext(row.canonical_careers_url),
                    resolved_careers_landing_url=row.canonical_careers_url,
                    source_jobs_search_url=row.operational_url,
                    portal_scope=row.source_scope,
                    ats_family=row.ats_family or _infer_ats_family(normalized),
                    ats_confidence=_ats_confidence_from_evidence(row.evidence_state),
                    portal_resolution_status=row.evidence_state,
                    portal_verification_url=row.evidence_url or row.canonical_careers_url,
                    # `portal_verified_date` is NOT NULL in the schema, so we
                    # have to write something on first insert. 2000-01-01 is
                    # the documented "unknown" sentinel for new mappings and
                    # is never confused with a real verification date.
                    portal_verified_date=verified_date or date(2000, 1, 1),
                    resolution_parent_override="",
                    resolution_wave=source_version,
                    source_record_count=0,
                    import_batch_id=batch.id,
                )
                session.add(mapping)
                session.flush()
                existing_mappings_by_key[key] = mapping
                created_mappings += 1
                action_counts["create_mapping"] += 1
            else:
                # Additive update: never disable, never delete. Refresh
                # evidence metadata but keep scan_enabled/active_in_registry
                # state from existing rows (which is owned by the runtime).
                mapping.portal_scope = row.source_scope or mapping.portal_scope
                mapping.ats_family = row.ats_family or mapping.ats_family
                mapping.ats_confidence = (
                    _ats_confidence_from_evidence(row.evidence_state) or mapping.ats_confidence
                )
                mapping.portal_resolution_status = row.evidence_state
                mapping.portal_verification_url = (
                    row.evidence_url or mapping.portal_verification_url
                )
                # Never overwrite a real verified date with a blank one from a
                # later CSV row — the operator has to explicitly retract it.
                if verified_date is not None:
                    mapping.portal_verified_date = verified_date
                mapping.resolution_wave = source_version
                mapping.import_batch_id = batch.id
                updated_mappings += 1
                action_counts["update_mapping"] += 1
            # Refresh portal aggregate every iteration so cluster_count stays
            # accurate even for reused portals.
            session.flush()
            _refresh_portal_aggregate(session, portal.id)

        after = _database_metrics(session)
        batch.status = "COMPLETED"
        batch.finished_at = utc_now()
        batch.row_count = len(rows)
        batch.cluster_count = after["portals"]
        batch.portal_count = after["portals"]
        multi_source_employers = sorted(
            employer for employer, count in per_employer_count.items() if count > 1
        )
        evidence = {
            "matched_employers": sorted(matched_employers),
            "unmatched_employers": sorted(unmatched_employers),
            "matched_rows": sum(per_employer_count.values()),
            "multi_source_employers": multi_source_employers,
            "created_portals": created_portals,
            "reused_portals": reused_portals,
            "created_mappings": created_mappings,
            "updated_mappings": updated_mappings,
            "action_counts": dict(action_counts),
            "before": before,
            "after": after,
            "total_rows": len(rows),
        }
        batch.validation_json = json.dumps(evidence, sort_keys=True, default=str)
        snapshot = SyncReport(
            import_batch_id=batch.id,
            source_sha256=source_sha,
            source_path=str(resolved),
            already_applied=False,
            matched_employers=tuple(sorted(matched_employers)),
            unmatched_employers=tuple(sorted(unmatched_employers)),
            matched_rows=sum(per_employer_count.values()),
            total_rows=len(rows),
            multi_source_employers=tuple(multi_source_employers),
            created_portals=created_portals,
            reused_portals=reused_portals,
            created_mappings=created_mappings,
            updated_mappings=updated_mappings,
            action_counts=dict(action_counts),
        )
    return snapshot


def _create_portal(session: Session, batch_id: int, normalized: str, row: OperationalSourceRow) -> Portal:
    parsed = urlsplit(normalized)
    portal = Portal(
        normalized_jobs_url=normalized,
        jobs_search_url=row.operational_url,
        scheme=parsed.scheme,
        host=parsed.hostname or "",
        ats_families_json=json.dumps([row.ats_family] if row.ats_family else []),
        ats_confidences_json=json.dumps(
            [_ats_confidence_from_evidence(row.evidence_state)]
            if row.ats_family
            else []
        ),
        metadata_conflict=False,
        cluster_count=0,
        active_in_registry=True,
        scan_enabled=row.scan_enabled,
        access_state="AVAILABLE",
        health_state="UNKNOWN",
        consecutive_failures=0,
        import_batch_id=batch_id,
    )
    session.add(portal)
    session.flush()
    return portal


def _refresh_portal_aggregate(session: Session, portal_id: int) -> None:
    portal = session.get(Portal, portal_id)
    if portal is None:
        return
    mappings = session.scalars(
        select(ClusterPortalMapping).where(ClusterPortalMapping.portal_id == portal_id)
    ).all()
    portal.cluster_count = len(mappings)
    portal.active_in_registry = bool(mappings)
    families = sorted({mapping.ats_family for mapping in mappings if mapping.ats_family})
    confidences = sorted({mapping.ats_confidence for mapping in mappings if mapping.ats_confidence})
    if families:
        portal.ats_families_json = json.dumps(families, ensure_ascii=False, separators=(",", ":"))
    if confidences:
        portal.ats_confidences_json = json.dumps(
            confidences, ensure_ascii=False, separators=(",", ":")
        )
    portal.metadata_conflict = len(families) > 1 or len(confidences) > 1
    if mappings:
        portal.jobs_search_url = sorted(
            {mapping.source_jobs_search_url for mapping in mappings}, key=str.casefold
        )[0]


def _load_existing_state(engine: Engine) -> tuple[set[str], set[tuple[str, str]]]:
    create_schema(engine)
    with Session(engine) as session:
        urls = {p.normalized_jobs_url for p in session.scalars(select(Portal)).all()}
        keys = {
            (m.corporate_cluster_id, p.normalized_jobs_url)
            for m, p in session.execute(
                select(ClusterPortalMapping, Portal).where(
                    ClusterPortalMapping.portal_id == Portal.id
                )
            ).all()
        }
    return urls, keys


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def urlsplitext(url: str) -> str:
    """Extract the scheme+host of a URL for `resolved_corporate_website`."""

    parsed = urlsplit(url)
    if not parsed.scheme or not parsed.hostname:
        return ""
    return f"{parsed.scheme}://{parsed.hostname}"


def _infer_ats_family(normalized: str) -> str:
    host = (urlsplit(normalized).hostname or "").lower()
    if "greenhouse.io" in host:
        return "Greenhouse"
    if "lever.co" in host:
        return "Lever"
    if "ashbyhq.com" in host:
        return "Ashby"
    if "smartrecruiters.com" in host:
        return "SmartRecruiters"
    if "talentbrew.com" in host or "radancy" in host:
        return "Radancy"
    if "successfactors" in host:
        return "SuccessFactors RMK"
    if "myworkdayjobs.com" in host:
        return "Workday"
    if "phenom" in host:
        return "Phenom"
    if "taleo" in host:
        return "Taleo"
    if "oraclecloud.com" in host:
        return "Oracle Recruiting Cloud"
    if "avature" in host:
        return "Avature"
    return ""


def _ats_confidence_from_evidence(evidence_state: str) -> str:
    if evidence_state in {
        "FIRST_PARTY_VERIFIED",
        "TECHNICALLY_VERIFIED",
        "FIRST_PARTY_AND_PLATFORM_VERIFIED",
        "OPERATIONAL_PLATFORM_VERIFIED",
        "GREENHOUSE_OPERATIONAL_PLATFORM_VERIFIED",
        "FIRST_PARTY_VERIFIED_PLATFORM",
        "TECHNICALLY_VERIFIED_PLATFORM",
    }:
        return "VERIFIED"
    if evidence_state == "PROBABLE":
        return "PROBABLE"
    return "UNVERIFIED"


def _database_metrics(session: Session) -> dict[str, int]:
    return {
        "portals": int(session.scalar(select(func.count()).select_from(Portal)) or 0),
        "cluster_portal_mappings": int(
            session.scalar(select(func.count()).select_from(ClusterPortalMapping)) or 0
        ),
    }


# ---------------------------------------------------------------------------
# Queue + summary generation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolutionSummary:
    core_200_employers: int  # distinct employer_name in CORE_200
    core_extension_employers: int  # distinct employer_name in CORE_EXTENSION
    distinct_employers: int  # distinct employer_name overall
    total_operational_sources: int  # number of source rows
    source_less_employers: int  # distinct employer_name with no operational_url
    multi_source_employers: tuple[str, ...]
    matched_employers: int
    unmatched_employers: int
    ready_to_probe_total: int
    ready_to_probe_by_ats: dict[str, int]
    fingerprint_required_total: int
    adapter_needed_total: int
    adapter_needed_by_platform: dict[str, int]
    resolver_light_total: int
    hold_total: int
    queue_counts: dict[str, int]


def build_resolution_summary(
    rows: list[OperationalSourceRow],
    *,
    cluster_mapping: dict[str, str],
) -> ResolutionSummary:
    """Group rows by `resolution_path` and cohort, producing the report payload.

    The summary uses distinct employer counts, NOT row counts, for every
    employer-level field. The `total_operational_sources` field is the only
    row-based counter. `source_less_employers` is the count of distinct
    employer names whose rows have empty `operational_url` — these are
    the registry's record of unresolved employers and do not produce any
    Portal / ClusterPortalMapping.
    """

    by_path: dict[str, list[OperationalSourceRow]] = defaultdict(list)
    for row in rows:
        by_path[row.resolution_path].append(row)
    per_employer: dict[str, int] = defaultdict(int)
    core_200: set[str] = set()
    core_extension: set[str] = set()
    matched_employers: set[str] = set()
    source_less_employers: set[str] = set()
    for row in rows:
        per_employer[row.employer_name] += 1
        if cluster_mapping.get(row.employer_name):
            matched_employers.add(row.employer_name)
        if not row.operational_url:
            source_less_employers.add(row.employer_name)
        if row.cohort == "CORE_200":
            core_200.add(row.employer_name)
        else:
            core_extension.add(row.employer_name)
    multi_source = sorted(e for e, count in per_employer.items() if count > 1)

    ready_total = len(by_path.get("READY_TO_PROBE", []))
    ready_by_ats: Counter[str] = Counter(
        row.ats_family or "Unknown"
        for row in by_path.get("READY_TO_PROBE", [])
        if row.ats_family
    )
    adapter_needed_rows = by_path.get("ADAPTER_NEEDED", [])
    adapter_by_platform: Counter[str] = Counter(
        row.ats_family or "Unknown" for row in adapter_needed_rows
    )
    return ResolutionSummary(
        core_200_employers=len(core_200),
        core_extension_employers=len(core_extension),
        distinct_employers=len(per_employer),
        total_operational_sources=len(rows),
        source_less_employers=len(source_less_employers),
        multi_source_employers=tuple(multi_source),
        matched_employers=len(matched_employers),
        unmatched_employers=len({r.employer_name for r in rows}) - len(matched_employers),
        ready_to_probe_total=ready_total,
        ready_to_probe_by_ats=dict(ready_by_ats),
        fingerprint_required_total=len(by_path.get("FINGERPRINT_REQUIRED", [])),
        adapter_needed_total=len(adapter_needed_rows),
        adapter_needed_by_platform=dict(adapter_by_platform),
        resolver_light_total=len(by_path.get("RESOLVER_LIGHT", [])),
        hold_total=len(by_path.get("HOLD", [])),
        queue_counts={queue: len(items) for queue, items in by_path.items()},
    )


def render_resolution_queues_csv(rows: list[OperationalSourceRow], destination: Path) -> Path:
    destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REGISTRY_HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))
    return destination


def write_resolution_summary_json(
    summary: ResolutionSummary,
    destination: Path,
) -> Path:
    destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "core_200_employers": summary.core_200_employers,
        "core_extension_employers": summary.core_extension_employers,
        "distinct_employers": summary.distinct_employers,
        "total_operational_sources": summary.total_operational_sources,
        "source_less_employers": summary.source_less_employers,
        "multi_source_employers": list(summary.multi_source_employers),
        "matched_employers": summary.matched_employers,
        "unmatched_employers": summary.unmatched_employers,
        "ready_to_probe_total": summary.ready_to_probe_total,
        "ready_to_probe_by_ats": summary.ready_to_probe_by_ats,
        "fingerprint_required_total": summary.fingerprint_required_total,
        "adapter_needed_total": summary.adapter_needed_total,
        "adapter_needed_by_platform": summary.adapter_needed_by_platform,
        "resolver_light_total": summary.resolver_light_total,
        "hold_total": summary.hold_total,
        "queue_counts": summary.queue_counts,
    }
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def write_unmatched_csv(
    unmatched: list[dict[str, str]],
    destination: Path,
) -> Path:
    destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("employer", "reason", "possible_candidates", "manual_review_required"),
        )
        writer.writeheader()
        for row in unmatched:
            writer.writerow(row)
    return destination


def render_terminal_summary(summary: ResolutionSummary) -> str:
    lines: list[str] = [
        "===== OPERATIONAL SOURCE CONTROL PLANE — SUMMARY =====",
        f"Distinct CORE_200 employers:            {summary.core_200_employers}",
        f"Distinct CORE_EXTENSION employers:      {summary.core_extension_employers}",
        f"Distinct employers (all cohorts):       {summary.distinct_employers}",
        f"Total operational source rows:          {summary.total_operational_sources}",
        f"Source-less unresolved employers:       {summary.source_less_employers}",
        f"Multi-source employers:                 {len(summary.multi_source_employers)}",
        f"Matched employers:                      {summary.matched_employers}",
        f"Unmatched employers:                    {summary.unmatched_employers}",
        "",
        "Resolution queues (row counts):",
        f"  READY_TO_PROBE     : {summary.ready_to_probe_total}",
        f"  FINGERPRINT_REQUIRED: {summary.fingerprint_required_total}",
        f"  ADAPTER_NEEDED     : {summary.adapter_needed_total}",
        f"  RESOLVER_LIGHT     : {summary.resolver_light_total}",
        f"  HOLD               : {summary.hold_total}",
        "",
        "READY_TO_PROBE by ATS family:",
    ]
    for family, count in sorted(summary.ready_to_probe_by_ats.items()):
        lines.append(f"  - {family}: {count}")
    lines.append("")
    lines.append("ADAPTER_NEEDED by platform:")
    if summary.adapter_needed_by_platform:
        for family, count in sorted(summary.adapter_needed_by_platform.items()):
            lines.append(f"  - {family}: {count}")
    else:
        lines.append("  (none)")
    lines.append("")
    if summary.multi_source_employers:
        lines.append("Multi-source employers (need union/dedup at probe time):")
        for employer in summary.multi_source_employers:
            lines.append(f"  - {employer}")
    return "\n".join(lines) + "\n"
