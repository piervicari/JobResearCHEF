# 0028 — Selective detail enrichment after first AI pass

**Status:** ACCEPTED / P0 IMPLEMENTATION  
**Date:** 2026-09-02

## Decision
Do not fetch every detail page during listing discovery. Use a two-stage acquisition flow:

```text
listing / ATS scan
      ↓
SourceJob + PENDING_AI
      ↓
first AI pass
      ↓
CYBER or NEEDS_MORE_DETAIL + description too short
      ↓
bounded official detail fetch
      ↓
store detail provenance separately
      ↓
PENDING_AI again
      ↓
AI re-analysis
```

CYBER rows are prioritized before NEEDS_MORE_DETAIL rows because even an obvious cyber title still needs the full description for skill/experience reverse engineering.

## Initial safety boundary
The first implementation only enriches `official_html` rows and only follows a same-host official job URL. It is deliberately limited, sequential, zero-retry, robots-aware and capped per run. Structured ATS-specific detail endpoints can be added later where needed.

## Data model
Keep listing data and detail data distinguishable. Add optional `detail_*` fields on SourceJob:

- detail_title
- detail_location / country / city
- detail_employment_type / workplace_type
- detail_description
- detail_url
- detail_payload_sha256
- detail_fetched_at

The original listing payload remains in the source observation/audit envelope.

## AI versioning correction
`JobAiAnalysis.input_payload_sha256` must identify the **effective AI input**, not merely the listing observation hash. Otherwise enriching a description would collide with an older analysis using the same prompt/model. The effective hash includes company/title/location/country/city/employment/workplace/description/source URL, preferring detail fields when present.

## Why
This gives full job evidence for skill mining without turning each portal scan into dozens/hundreds of requests.
