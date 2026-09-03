# Decision 0007: Evidence-backed internship and graduate-program intelligence

- Status: Deferred after usable cyber scanner
- Date: 2026-09-02

## Decision

Create a separate research capability for questions such as:

- Does this company historically offer internships or graduate programs?
- Has it offered cybersecurity internships specifically?
- In which locations/years have programs been observed?

This is separate from the live career-site scanner and must not block the first usable release.

## Implementation principle

Do not ask an LLM to answer from model memory alone.

```text
CODE
web search / official-source discovery / fetch / cache
        ↓
LLM
extract, reconcile and classify evidence
        ↓
structured program record with source URLs and dates
```

Possible record:

```json
{
  "company_id": "...",
  "program_type": "internship",
  "cyber_observed": true,
  "observed_years": [2024, 2025, 2026],
  "locations": ["..."],
  "last_verified_at": "...",
  "evidence": ["source-reference"]
}
```

## Why

Historical program behavior can reveal opportunities before a vacancy is currently open, but the
information changes slowly and does not need multiple daily checks.

## Deferred extensions

- program opening calendar;
- seasonal scan-frequency boost around historically active windows.
