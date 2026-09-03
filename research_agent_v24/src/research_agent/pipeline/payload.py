"""Application-owned observation payloads for stable hashing and auditability.

The ATS/native payload is preserved for debugging, but it does not define whether a
vacancy changed.  Change detection is based on the fields the application actually
cares about so adapters cannot accidentally omit location/title/description from the
hash contract.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any

from research_agent.sources.base import RawJob


PAYLOAD_SCHEMA_VERSION = "job-observation-v1"


def canonical_job_payload(
    raw_job: RawJob,
    *,
    company_id: str | None,
    company_name: str,
    adapter: str,
) -> dict[str, Any]:
    """Return the stable application-owned representation of one observed vacancy."""

    return {
        "schema_version": PAYLOAD_SCHEMA_VERSION,
        "company_id": company_id,
        "company_name_raw": raw_job.company,
        "company_name_resolved": company_name or raw_job.company,
        "source": raw_job.source,
        "source_job_id": raw_job.source_job_id,
        "ats_job_id": raw_job.ats_job_id,
        "requisition_id": raw_job.requisition_id,
        "job_title": raw_job.title,
        "location": raw_job.location,
        "country": raw_job.country,
        "city": raw_job.city,
        "job_description": raw_job.description,
        "source_url": raw_job.source_url,
        "apply_url": raw_job.apply_url,
        "employment_type": raw_job.employment_type,
        "workplace_type": raw_job.workplace_type,
        "posted_at": raw_job.posted_at,
        "adapter": adapter,
    }


def serialize_observation_payload(
    raw_job: RawJob,
    *,
    company_id: str | None,
    company_name: str,
    adapter: str,
) -> tuple[str, str]:
    """Return ``(audit_json, content_sha256)`` for a vacancy observation.

    ``audit_json`` contains both our canonical representation and the original
    adapter payload. ``content_sha256`` hashes only the canonical representation;
    provider-specific volatile fields therefore cannot create false content changes.
    """

    canonical = canonical_job_payload(
        raw_job,
        company_id=company_id,
        company_name=company_name,
        adapter=adapter,
    )
    canonical_json = _dumps(canonical)
    envelope = {
        "canonical": canonical,
        "source_native_payload": raw_job.raw_payload,
    }
    return _dumps(envelope), hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _dumps(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )


def _json_default(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)
