# Decision 0003: Simplified official career portal resolution

- Status: Accepted
- Date: 2026-09-02

## Decision

Portal resolution should optimize for a trustworthy, usable official jobs endpoint rather than for a
fully researched corporate/ATS dossier before the company can be scanned.

An ATS is an Applicant Tracking System (for example Workday, Greenhouse, Lever, SuccessFactors,
SmartRecruiters, Ashby, Oracle Recruiting or Avature). ATS identification is useful for structured
fetching but is **not a prerequisite** for adding a valid official career/jobs URL to the registry.

## Why

Previous waves were intentionally conservative: they tried to verify corporate ownership, careers
landing page, jobs endpoint, ATS, parent/subsidiary relationships, scope, evidence and confidence before
marking a portal resolved. This maximizes dataset purity but produces many deferred cases and slows the
path to a usable product.

For the operational target-company set, the minimum useful truth is: "this official source publishes
this company's jobs and can be scanned safely".

## Minimal implementation shape

```json
{
  "company_id": "...",
  "company_name": "...",
  "official_domain": "example.com",
  "jobs_url": "https://...",
  "status": "active",
  "verified_at": "2026-09-02T..."
}
```

Optional fields remain valuable when known:

```json
{
  "ats_family": "workday",
  "resolution_notes": "...",
  "confidence": "high"
}
```

## Trade-offs / challenges

Simplification must not become careless mapping. A wrong company→portal association contaminates every
job downstream. Keep cheap ownership/official-source verification, but do not block scanning merely
because ATS family, parent structure or geographic scope is not yet perfectly classified.
