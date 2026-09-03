# ADR 0011: Reviewed company aliases and read-only fuzzy proposals

Date: 2026-08-31

## Decision

External company names resolve automatically only through an exact unambiguous master name or an
exact unambiguous alias whose status is `VERIFIED`. Aliases carry provenance, evidence and an
immutable import batch. `PROPOSED` aliases never participate in resolution.

Fuzzy similarity is available only as a ranked operator aid. It cannot insert an alias, update a
source job or assign a corporate cluster. Promotion from proposed to verified requires a later
reviewed artifact; demotion is rejected.

## Consequences

Recall grows through reviewable evidence while automatic false company assignments remain bounded.
Short acronyms and brand names can stay unresolved indefinitely without corrupting cluster history.
