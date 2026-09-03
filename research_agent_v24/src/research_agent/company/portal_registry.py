"""Build a deduplicated portal registry without discarding cluster provenance."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit, urlunsplit


class PortalRegistryError(ValueError):
    pass


def normalize_jobs_url(raw_url: str) -> str:
    """Normalize only URL syntax that is safe for endpoint identity.

    Query strings and paths are deliberately preserved because they can select a tenant,
    locale or employer. Fragments are never sent to the server and can be removed safely.
    """

    value = raw_url.strip()
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise PortalRegistryError(f"Invalid jobs URL: {raw_url!r}") from exc

    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower().rstrip(".")
    if scheme not in {"http", "https"} or not host:
        raise PortalRegistryError(f"Jobs URL must be absolute HTTP(S): {raw_url!r}")
    if parsed.username or parsed.password:
        raise PortalRegistryError(f"Credentials are not allowed in jobs URL: {raw_url!r}")

    netloc = host
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"

    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")

    normalized = SplitResult(scheme, netloc, path, parsed.query, "")
    return urlunsplit(normalized)


@dataclass(frozen=True)
class ClusterPortal:
    corporate_cluster_id: str
    normalized_jobs_url: str
    source_jobs_search_url: str
    resolved_corporate_website: str
    resolved_careers_landing_url: str
    portal_scope: str
    ats_family: str
    ats_confidence: str
    portal_resolution_status: str
    portal_verification_url: str
    portal_verified_date: str
    resolution_parent_override: str
    resolution_wave: str
    source_record_count: int


@dataclass(frozen=True)
class PortalRegistryEntry:
    normalized_jobs_url: str
    jobs_search_url: str
    scheme: str
    host: str
    ats_families: tuple[str, ...]
    ats_confidences: tuple[str, ...]
    cluster_ids: tuple[str, ...]
    metadata_conflict: bool


@dataclass(frozen=True)
class PortalRegistryBuild:
    portals: tuple[PortalRegistryEntry, ...]
    mappings: tuple[ClusterPortal, ...]


_CLUSTER_RESOLUTION_FIELDS = (
    "Resolved Corporate Website",
    "Resolved Careers Landing URL",
    "Resolved Jobs Search URL",
    "Portal Scope",
    "ATS Family",
    "ATS Confidence",
    "Portal Resolution Status",
    "Portal Verification URL",
    "Portal Verified Date",
    "Resolution Parent Override",
    "Resolution Wave",
)


def build_portal_registry(rows: list[dict[str, str]]) -> PortalRegistryBuild:
    resolved_by_cluster: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row["Resolution Wave"].strip():
            resolved_by_cluster[row["Corporate Cluster ID"].strip()].append(row)

    mappings: list[ClusterPortal] = []
    for cluster_id, cluster_rows in sorted(resolved_by_cluster.items()):
        representative = cluster_rows[0]
        for field in _CLUSTER_RESOLUTION_FIELDS:
            values = {row[field].strip() for row in cluster_rows}
            if len(values) != 1:
                raise PortalRegistryError(
                    f"Cluster {cluster_id} has conflicting values for {field}: {sorted(values)}"
                )

        raw_url = representative["Resolved Jobs Search URL"].strip()
        mappings.append(
            ClusterPortal(
                corporate_cluster_id=cluster_id,
                normalized_jobs_url=normalize_jobs_url(raw_url),
                source_jobs_search_url=raw_url,
                resolved_corporate_website=representative["Resolved Corporate Website"].strip(),
                resolved_careers_landing_url=representative["Resolved Careers Landing URL"].strip(),
                portal_scope=representative["Portal Scope"].strip(),
                ats_family=representative["ATS Family"].strip(),
                ats_confidence=representative["ATS Confidence"].strip(),
                portal_resolution_status=representative["Portal Resolution Status"].strip(),
                portal_verification_url=representative["Portal Verification URL"].strip(),
                portal_verified_date=representative["Portal Verified Date"].strip(),
                resolution_parent_override=representative["Resolution Parent Override"].strip(),
                resolution_wave=representative["Resolution Wave"].strip(),
                source_record_count=len(cluster_rows),
            )
        )

    by_url: dict[str, list[ClusterPortal]] = defaultdict(list)
    for mapping in mappings:
        by_url[mapping.normalized_jobs_url].append(mapping)

    portals: list[PortalRegistryEntry] = []
    for normalized_url, portal_mappings in sorted(by_url.items()):
        parsed = urlsplit(normalized_url)
        ats_families = tuple(sorted({item.ats_family for item in portal_mappings}))
        ats_confidences = tuple(sorted({item.ats_confidence for item in portal_mappings}))
        raw_urls = sorted({item.source_jobs_search_url for item in portal_mappings})
        portals.append(
            PortalRegistryEntry(
                normalized_jobs_url=normalized_url,
                jobs_search_url=raw_urls[0],
                scheme=parsed.scheme,
                host=parsed.hostname or "",
                ats_families=ats_families,
                ats_confidences=ats_confidences,
                cluster_ids=tuple(sorted(item.corporate_cluster_id for item in portal_mappings)),
                metadata_conflict=len(ats_families) > 1 or len(ats_confidences) > 1,
            )
        )

    return PortalRegistryBuild(portals=tuple(portals), mappings=tuple(mappings))
