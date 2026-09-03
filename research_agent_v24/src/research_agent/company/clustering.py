"""Conservative vacancy-to-cluster resolution for shared portals."""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from research_agent.db.models import ClusterPortalMapping, CompanyAlias, CorporateCluster
from research_agent.filters.common import normalize_text


@dataclass(frozen=True)
class ClusterResolution:
    corporate_cluster_id: str | None
    method: str
    candidate_cluster_ids: tuple[str, ...]


class PortalClusterResolver:
    def __init__(self, session: Session) -> None:
        rows = session.execute(
            select(ClusterPortalMapping, CorporateCluster).join(
                CorporateCluster,
                CorporateCluster.corporate_cluster_id
                == ClusterPortalMapping.corporate_cluster_id,
            )
        ).all()
        self._by_portal: dict[int, list[tuple[ClusterPortalMapping, CorporateCluster]]] = {}
        for mapping, cluster in rows:
            self._by_portal.setdefault(mapping.portal_id, []).append((mapping, cluster))
        clusters = session.scalars(select(CorporateCluster)).all()
        self._clusters_by_id = {cluster.corporate_cluster_id: cluster for cluster in clusters}
        self._global_name_to_clusters: dict[str, set[str]] = {}
        self._verified_alias_to_clusters: dict[str, set[str]] = {}
        self._verified_aliases_by_cluster: dict[str, set[str]] = {}
        for cluster in clusters:
            names = {
                cluster.representative_canonical_employer,
                *json.loads(cluster.canonical_employers_json),
                *json.loads(cluster.parent_groups_json),
            }
            for name in names:
                if normalized := normalize_text(name):
                    self._global_name_to_clusters.setdefault(normalized, set()).add(
                        cluster.corporate_cluster_id
                    )
        aliases = session.scalars(
            select(CompanyAlias).where(CompanyAlias.status == "VERIFIED")
        ).all()
        for alias in aliases:
            self._verified_alias_to_clusters.setdefault(alias.normalized_alias, set()).add(
                alias.corporate_cluster_id
            )
            self._verified_aliases_by_cluster.setdefault(alias.corporate_cluster_id, set()).add(
                alias.normalized_alias
            )

    def resolve(self, *, portal_id: int, raw_company: str) -> ClusterResolution:
        candidates = self._by_portal.get(portal_id, [])
        candidate_ids = tuple(sorted(cluster.corporate_cluster_id for _, cluster in candidates))
        if not candidates:
            return ClusterResolution(None, "portal_has_no_cluster_mapping", ())
        if len(candidates) == 1:
            return ClusterResolution(candidate_ids[0], "single_portal_mapping", candidate_ids)

        normalized_company = normalize_text(raw_company)
        if not normalized_company:
            return ClusterResolution(None, "shared_portal_missing_company", candidate_ids)

        exact_matches: list[str] = []
        for mapping, cluster in candidates:
            names = {
                normalize_text(cluster.representative_canonical_employer),
                normalize_text(mapping.resolution_parent_override),
                *(
                    normalize_text(value)
                    for value in json.loads(cluster.canonical_employers_json)
                ),
                *(normalize_text(value) for value in json.loads(cluster.parent_groups_json)),
                *self._verified_aliases_by_cluster.get(cluster.corporate_cluster_id, set()),
            }
            names.discard("")
            if normalized_company in names:
                exact_matches.append(cluster.corporate_cluster_id)

        unique_matches = tuple(sorted(set(exact_matches)))
        if len(unique_matches) == 1:
            return ClusterResolution(unique_matches[0], "exact_company_name", candidate_ids)
        if unique_matches:
            return ClusterResolution(None, "ambiguous_exact_company_name", unique_matches)
        return ClusterResolution(None, "shared_portal_no_exact_company_match", candidate_ids)

    def display_company_name(
        self,
        *,
        portal_id: int | None,
        raw_company: str,
        resolution: ClusterResolution,
    ) -> str:
        """Return a transparent employer/group label without inventing cluster precision."""

        if resolution.corporate_cluster_id is not None:
            cluster = self._clusters_by_id.get(resolution.corporate_cluster_id)
            if cluster is not None:
                return cluster.representative_canonical_employer
        if raw_company.strip():
            return raw_company.strip()

        if portal_id is not None:
            candidates = self._by_portal.get(portal_id, [])
            parent_overrides = {
                mapping.resolution_parent_override.strip()
                for mapping, _ in candidates
                if mapping.resolution_parent_override.strip()
            }
            if len(parent_overrides) == 1:
                return next(iter(parent_overrides))
            names = [cluster.representative_canonical_employer for _, cluster in candidates]
            common = _common_word_prefix(names)
            if common:
                return common
            if names:
                return " / ".join(dict.fromkeys(names))
        return ""

    def resolve_company(self, raw_company: str) -> ClusterResolution:
        normalized = normalize_text(raw_company)
        if not normalized:
            return ClusterResolution(None, "external_source_missing_company", ())
        candidates = tuple(sorted(self._global_name_to_clusters.get(normalized, set())))
        if len(candidates) == 1:
            return ClusterResolution(candidates[0], "global_exact_company_name", candidates)
        if candidates:
            return ClusterResolution(None, "global_ambiguous_company_name", candidates)
        alias_candidates = tuple(
            sorted(self._verified_alias_to_clusters.get(normalized, set()))
        )
        if len(alias_candidates) == 1:
            return ClusterResolution(
                alias_candidates[0], "global_verified_company_alias", alias_candidates
            )
        if alias_candidates:
            return ClusterResolution(None, "global_ambiguous_verified_alias", alias_candidates)
        return ClusterResolution(None, "global_company_name_not_found", ())


def _common_word_prefix(names: list[str]) -> str:
    if not names:
        return ""
    tokenized = [name.split() for name in names if name.strip()]
    if not tokenized:
        return ""
    prefix: list[str] = []
    for position in range(min(len(tokens) for tokens in tokenized)):
        values = {tokens[position].casefold() for tokens in tokenized}
        if len(values) != 1:
            break
        prefix.append(tokenized[0][position])
    return " ".join(prefix)
