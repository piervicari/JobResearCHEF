"""Stable, explainable source and cross-source vacancy deduplication."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from research_agent.filters.common import normalize_text
from research_agent.pipeline.normalizer import normalize_location, normalize_title

_TRACKING_QUERY_NAMES = {
    "gh_src",
    "lever-source",
    "lever_via",
    "ref",
    "referrer",
    "source",
    "src",
    "trid",
}


def canonical_application_url(value: str) -> str:
    stripped = value.strip()
    parsed = urlsplit(stripped)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return stripped
    scheme = parsed.scheme.lower()
    host = parsed.hostname.lower().rstrip(".")
    port = parsed.port
    netloc = host
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_")
        and key.casefold() not in _TRACKING_QUERY_NAMES
    ]
    query = urlencode(sorted(query_items), doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


def source_identity(source: str, source_job_id: str) -> str:
    return f"{normalize_text(source)}\0{source_job_id.strip()}"


def ats_identity(corporate_cluster_id: str, ats_job_id: str | None) -> str | None:
    value = (ats_job_id or "").strip()
    return f"{corporate_cluster_id.strip()}\0{value}" if value else None


def canonical_fingerprint(
    *,
    corporate_cluster_id: str,
    title: str,
    location: str,
    requisition_id: str | None = None,
) -> str:
    payload = "\0".join(
        (
            corporate_cluster_id.strip(),
            normalize_title(title),
            normalize_location(location),
            normalize_text(requisition_id or ""),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DedupCandidate:
    canonical_job_id: str
    source: str
    source_job_id: str
    apply_url: str
    corporate_cluster_id: str
    title: str
    location: str
    ats_job_id: str | None = None
    requisition_id: str | None = None


@dataclass(frozen=True)
class DedupMatch:
    canonical_job_id: str
    method: str


class DedupIndex:
    """In-memory exact index; fuzzy matching is intentionally not part of the MVP path."""

    def __init__(self) -> None:
        self._source: dict[str, DedupCandidate] = {}
        self._apply_url: dict[str, DedupCandidate] = {}
        self._ats_id: dict[str, DedupCandidate] = {}
        self._fingerprint: dict[str, DedupCandidate] = {}

    def add(self, candidate: DedupCandidate) -> None:
        self._source[source_identity(candidate.source, candidate.source_job_id)] = candidate
        if canonical_url := canonical_application_url(candidate.apply_url):
            self._apply_url[canonical_url] = candidate
        if ats_id := ats_identity(candidate.corporate_cluster_id, candidate.ats_job_id):
            self._ats_id[ats_id] = candidate
        self._fingerprint[
            canonical_fingerprint(
                corporate_cluster_id=candidate.corporate_cluster_id,
                title=candidate.title,
                location=candidate.location,
                requisition_id=candidate.requisition_id,
            )
        ] = candidate

    def match(self, candidate: DedupCandidate) -> DedupMatch | None:
        source_key = source_identity(candidate.source, candidate.source_job_id)
        if existing := self._source.get(source_key):
            if _identity_compatible(existing, candidate):
                return DedupMatch(existing.canonical_job_id, "source_job_id")

        canonical_url = canonical_application_url(candidate.apply_url)
        if canonical_url and (existing := self._apply_url.get(canonical_url)):
            if _identity_compatible(existing, candidate):
                return DedupMatch(existing.canonical_job_id, "canonical_apply_url")

        if (ats_id := ats_identity(candidate.corporate_cluster_id, candidate.ats_job_id)) and (
            existing := self._ats_id.get(ats_id)
        ):
            if _identity_compatible(existing, candidate):
                return DedupMatch(existing.canonical_job_id, "ats_job_id")

        fingerprint = canonical_fingerprint(
            corporate_cluster_id=candidate.corporate_cluster_id,
            title=candidate.title,
            location=candidate.location,
            requisition_id=candidate.requisition_id,
        )
        if existing := self._fingerprint.get(fingerprint):
            return DedupMatch(existing.canonical_job_id, "normalized_fingerprint")
        return None


def _identity_compatible(existing: DedupCandidate, incoming: DedupCandidate) -> bool:
    """Reject an exact-ID merge when observable vacancy dimensions conflict.

    Missing values are not treated as conflicts. This intentionally prefers an
    occasional duplicate over silently dropping a city/title variant.
    """

    old_title = normalize_title(existing.title)
    new_title = normalize_title(incoming.title)
    if old_title and new_title and old_title != new_title:
        return False

    old_location = normalize_location(existing.location)
    new_location = normalize_location(incoming.location)
    if old_location and new_location and old_location != new_location:
        return False

    old_url = canonical_application_url(existing.apply_url)
    new_url = canonical_application_url(incoming.apply_url)
    if old_url and new_url and old_url != new_url:
        return False
    return True
