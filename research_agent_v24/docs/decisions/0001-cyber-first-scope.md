# Decision 0001: Cyber-first scope, retaining every cyber seniority

- Status: Accepted
- Date: 2026-09-02

## Decision

The first usable product focuses only on cybersecurity-related vacancies.
Within cybersecurity, **no vacancy is discarded because of seniority**: internship, graduate, junior,
mid, senior, staff, principal, manager and higher levels are all retained.

AI and software-engineering domains are deliberately postponed until the cyber pipeline is proven.
The data model should nevertheless allow multi-domain classification later, including overlaps such as
AI Security and Application Security.

## Why

- The immediate goal is to make the system useful as soon as possible.
- Senior postings are valuable even when not directly applicable: they reveal future skills, career
  ladders, certifications and experience expectations.
- Expanding to AI/SWE before validating cyber would increase scope and make failures harder to diagnose.

## Implementation shape

```text
company career portals
        ↓
discovered vacancies
        ↓
LLM semantic classification
        ↓
cyber? ── no → do not persist as a cyber job
  │
 yes
  ↓
STORE regardless of seniority
```

Future-compatible domain representation:

```json
{
  "domains": ["cybersecurity"]
}
```

Possible future overlap:

```json
{
  "domains": ["cybersecurity", "artificial_intelligence", "software_engineering"]
}
```

## Trade-offs / challenges

- "Cyber" cannot be defined only by literal title keywords. Roles such as Technology Risk, IAM,
  Product Security, Privacy Engineering or Trust Engineering can be cyber-relevant without using the
  word "cyber".
- Therefore semantic classification must have enough source context. Ambiguous listing-only records
  must not be silently discarded before detail enrichment if the title alone is insufficient.
- Non-cyber jobs may be transiently fetched/classified, but the V1 persistent research dataset is cyber-first.

## Current implementation impact

The current runtime filters for cyber **and** early-career/seniority. Seniority exclusion must be removed
from the ingestion path. Cyber classification itself will migrate from deterministic rules to LLM-based
semantic analysis (Decision 0004).
