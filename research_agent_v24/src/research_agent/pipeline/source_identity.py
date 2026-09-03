"""Conservative source-vacancy identity handling.

Provider IDs are useful hints, not infallible truth. If the same native source ID is
observed with materially different location/title/application URL, keep a distinct
variant rather than silently collapsing a vacancy.
"""

from __future__ import annotations

import hashlib

from research_agent.pipeline.dedup import canonical_application_url
from research_agent.pipeline.normalizer import normalize_location, normalize_title
from research_agent.sources.base import RawJob


def source_identity_conflicts(
    *,
    existing_title: str,
    existing_location: str,
    existing_apply_url: str,
    incoming: RawJob,
) -> bool:
    old_title = normalize_title(existing_title)
    new_title = normalize_title(incoming.title)
    if old_title and new_title and old_title != new_title:
        return True

    old_location = normalize_location(existing_location)
    new_location = normalize_location(incoming.location)
    if old_location and new_location and old_location != new_location:
        return True

    old_url = canonical_application_url(existing_apply_url)
    new_url = canonical_application_url(incoming.apply_url)
    if old_url and new_url and old_url != new_url:
        return True
    return False


def variant_source_job_id(raw_job: RawJob) -> str:
    """Create a deterministic storage identity for a conflicting source-ID variant."""

    native = raw_job.source_job_id.strip() or "anonymous"
    material = "\0".join(
        (
            native,
            normalize_title(raw_job.title),
            normalize_location(raw_job.location),
            canonical_application_url(raw_job.apply_url),
            (raw_job.requisition_id or "").strip(),
        )
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"{native}::variant:{digest}"
