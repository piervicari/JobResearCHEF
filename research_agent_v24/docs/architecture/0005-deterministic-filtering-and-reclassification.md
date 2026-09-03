# ADR 0005: Deterministic filtering with auditable review state

- Status: Accepted
- Date: 2026-08-30

## Context

Cybersecurity coverage must be broad while generic software, vendor-side sales/content roles,
explicitly senior roles and out-of-scope geographies must not become target jobs. ATS payloads often
omit seniority or country, so binary filtering would silently discard potentially useful records or
admit false positives.

## Decision

- Cyber, seniority and geography rules are configured in versioned YAML and tested independently.
- The combined result is `INCLUDE`, `REVIEW` or `EXCLUDE`; ambiguity is preserved as `REVIEW`.
- Description-only cyber matches require an early-career signal unless the title itself is clearly
  cyber. Generic SWE and explicit non-target functions are excluded first.
- Geography is evaluated on the vacancy, never inferred from company discovery geography.
- Every observation stores the full filter decision and cluster-resolution decision as JSON.
- Stored active source jobs can be reclassified without network access. Reclassification creates a
  run and immutable observations while keeping the original source adapter and raw provenance.

## Consequences

Rules are reproducible and corrections do not require re-scraping. Precision/recall is not yet
statistically measured; a labeled benchmark is required before tuning beyond the deterministic MVP.
