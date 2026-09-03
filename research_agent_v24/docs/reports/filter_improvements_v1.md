# Filtering and company identity improvements

Date: 2026-08-31

## Benchmark delta

Before the rule changes, the expanded 200-case benchmark passed with cyber 98.0%, seniority 98.0%,
geography 100.0% and final decision 99.5%. After the changes and twelve new regression cases, the
212-case benchmark passes with cyber 100.0%, seniority 98.1%, geography 100.0% and final decision
100.0%. INCLUDE precision and recall are both 100% for the final decision.

The four remaining component mismatches are the preserved product-policy cases where a functional
title contains `manager` together with an internship/graduate marker. They do not alter final
decisions because the roles are non-cyber functions. The implementation continues to prefer review
or exclusion over inferring junior status from an unsafe conflict.

## Seniority

- Bounded `0-2`, `0-3` and equivalent ranges are junior evidence.
- Ranges crossing three years and open-ended `3+` requirements are `REVIEW`.
- Requirements strictly above three years are `EXCLUDE`.
- A junior/intern marker that conflicts with a higher experience requirement is `REVIEW`.
- Ordinal level I/1 is junior, II/2 is employer-dependent (`REVIEW`), and III/3+ is excluded.

## Geography

A structured target country is included and a configured known out-of-scope country is excluded. An
unknown structured value is now `REVIEW`, with a distinct reason, instead of being silently treated
as out of scope. Existing adapters already consume structured country/city fields where their public
contracts expose them (Oracle, SmartRecruiters, Lever, Ashby, Avature, Phenom and JSON-LD fallback);
tests cover representative structured fields before free-text aliases are consulted.

## Company identity

The additive `company_aliases` table records alias, cluster, status, provenance, evidence reference,
reason and import batch. Only `VERIFIED` aliases may resolve an external company name. `PROPOSED`
aliases are deliberately ignored by resolution.

`company_aliases_v1.csv` imported four verified master-backed variants and two proposed acronyms.
The fuzzy command returns ranked candidates but performs no write; tests assert the alias table is
unchanged after a proposal call.

## Offline reclassification

Run 27 reclassified 5,228 active source jobs without network access: 0 INCLUDE, 40 REVIEW and 5,188
EXCLUDE. It updated 39 canonical jobs and consolidated two orphaned canonical identities after exact
deduplication; no source job was closed by absence. The absence of INCLUDE results is evidence about
the currently observed cohort, not a relaxation target.
