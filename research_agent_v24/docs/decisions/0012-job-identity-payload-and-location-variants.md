# 0012 — Job identity, canonical observation payload, and location variants

Status: **ACCEPTED + IMPLEMENTED IN V2 INGESTION**  
Date: 2026-09-02

## Context

The same employer may publish multiple vacancies with the same or recycled description for different cities. A content hash or description-only deduplication can therefore incorrectly collapse distinct job postings.

The existing implementation is already safer than description-only deduplication: it uses source IDs, URLs, ATS IDs, and a fallback fingerprint containing company cluster + title + location + requisition ID. However, two weaknesses remain:

1. `payload_sha256` may currently be computed from adapter-specific `raw_payload`, whose field coverage is not guaranteed to be identical across ATS adapters.
2. Strong dedup paths (`source_job_id`, canonical apply URL, ATS job ID) can theoretically merge location variants before the location-aware fallback fingerprint is reached.

False merges are more damaging than harmless duplicates because a missing city-specific opportunity becomes invisible.

## Decision

Separate three concepts explicitly:

1. **Source identity** — which source-side posting was observed.
2. **Canonical job identity** — whether two source observations represent the same vacancy.
3. **Content/version hash** — whether the observable contents of the same vacancy changed.

Never use job description alone as an identity key.

### Canonical observation payload

Build an application-owned canonical observation payload for every discovered posting, independent of the adapter's raw payload. It must contain at minimum:

```text
source
source_job_id
ats_job_id
requisition_id
company_id / corporate_cluster_id
company_name_raw
job_title_raw
location_raw
country_raw
city_raw
workplace_type_raw
employment_type_raw
description_raw
source_url
apply_url
posted_at
adapter
```

`fetched_at` / scan timestamps are observation metadata and MUST NOT participate in the content hash, otherwise every scan would appear to change the posting.

Keep the original adapter `raw_payload` separately for audit/debugging when available.

`payload_sha256` / content hash must be computed from the canonical observation payload, not from an arbitrary ATS-specific payload shape.

### Location-safe identity policy

Deduplication must be conservative.

Preferred evidence order:

1. exact stable source identity when unambiguous;
2. canonical posting/apply URL when it identifies one posting;
3. ATS/requisition identity **with location compatibility**;
4. fallback fingerprint containing employer + normalized title + normalized location + requisition ID.

If the same ATS/source ID is observed in the same run with conflicting city/location or distinct apply URLs, DO NOT silently discard the second observation. Record an identity collision and keep the variants distinct unless the adapter can prove that the provider represents them as one multi-location vacancy.

Different city/location + same/recycled description MUST NOT be merged merely because title/description match.

If useful later, related city variants may share a separate `requisition_group_id`; grouping is not deduplication.

## Raw vs AI fields

Preserve the exact source title as `job_title_raw` / equivalent. The AI-normalized role (e.g. `Security Engineering`, `GRC`) is separate AI analysis and never replaces the original title.

## Why

- prevents missing city-specific vacancies;
- preserves source truth;
- allows safe historical change detection;
- keeps dedup explainable;
- lets us tolerate duplicates rather than risk false merges.

## Trade-off

A conservative policy may retain occasional duplicate postings. This is accepted: duplicate rows can be merged later, whereas a falsely merged opportunity cannot be reconstructed reliably after ingestion.


## Implementation note — 2026-09-02

V2 now builds an application-owned `job-observation-v1` envelope containing raw and resolved company identity, native source ID, ATS/requisition IDs, raw title, location/country/city, full description, URLs, employment/workplace types, posted date and adapter. `payload_sha256` hashes the canonical application-owned portion only; provider-native JSON is preserved separately inside the audit envelope and cannot create false content changes through volatile fields.

If an existing `(source, native source_job_id)` conflicts on non-empty title/location/apply URL, V2 creates a deterministic `::variant:<hash>` storage identity while retaining the original native ID. Strong canonical dedup evidence is likewise rejected when observable vacancy dimensions conflict.
