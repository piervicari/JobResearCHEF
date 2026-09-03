# ADR 0013: Prioritized and deferred portal-resolution waves

Date: 2026-08-31

## Context

More than eleven thousand company clusters remain unresolved. Exhaustive discovery would be slow and
would encourage unsafe same-name or parent guesses. The source rows do not contain reviewed candidate
URLs for unresolved clusters.

## Decision

Resolution waves begin with a deterministic, review-only ranking over employer scale, cybersecurity
relevance, configured target geography, early-career probability, cluster record count and an
explicitly labeled ATS-quality proxy. The proxy measures employer maturity and identity clarity; it
does not claim that an ATS exists.

Only official corporate, careers and public job-search endpoints supported by evidence become
versioned registry `ADD` rows. Every selected cluster without approved evidence remains `DEFERRED`,
with blank endpoint fields and no registry mutation. Acquisitions, organizational units, ambiguous
acronyms and country-specific parent sharing require separate identity review.

Each wave ships the frozen selection, reviewed decisions, complete outcome and audit tables, summary,
registry batch, synchronized master and deterministic ZIP. Historical masters are verified by hash
and never overwritten.

## Consequences

Recall grows more slowly, but every automatic scan target has reviewable provenance. A wave may be
complete with deferred rows: completeness means every selected row has a safe outcome, not that a
mapping was forced. Ranking and artifact generation remain reproducible and testable offline.
