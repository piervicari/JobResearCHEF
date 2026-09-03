# 0049 — Google Careers uses its anonymous structured batchexecute RPC

**Status:** Accepted / implemented in V24  
**Date:** 2026-09-02

## Decision

Google Tier-S discovery uses a dedicated `GoogleCareersAdapter` for the verified `Custom Google Careers` platform rather than generic HTML extraction.

The adapter replays the anonymous BOQ endpoint used by the Google Careers frontend:

`POST /about/careers/applications/_/HiringCportalFrontendUi/data/batchexecute`

with `r06xKb` for search pagination. The request is form-encoded through the shared `HttpFetcher`; no browser, cookie, CSRF token, build id or referer is required by the observed endpoint.

The adapter is selected from the portal/platform signature (Google Careers host/path + ATS family), not from a corporate-cluster ID or `if company == Google` branch.

The positional response contract is pinned by tests: job id/title/apply URL, responsibilities, qualifications, company, locations, description, timestamps and minimum qualifications. Search records already contain substantive descriptions, so the initial Google probe does not fetch one detail page per job.

## Why

The public results page is server-rendered but paginates at 20 jobs per page. Generic HTML would require parsing navigation/UI and risks repeating the CTA false-job problem already seen in V23. The structured RPC exposes the same inventory in machine-readable records and preserves source IDs/descriptions directly.

## Alternatives rejected

- **Generic HTML pagination:** more brittle, mixes presentation with data, and conflicts with the project's structured-source-first rule.
- **Search only for `security`:** rejected for discovery because Google free-text search is fuzzy and would make raw-catalog completeness depend on query semantics.
- **Fetch every job detail page:** unnecessary for the initial catalog because the search RPC already carries the descriptive fields needed by triage/full analysis.

## Trade-offs

This is an internal, positional Google frontend contract rather than a documented public API. It may change. Strict schema validation and tests make breakage fail visibly rather than silently producing bad jobs. The public Google permalink remains the `SourceJob.source_url`.
