# Taxonomy benchmark design

Date: 2026-08-31

The benchmark contains 212 labeled vacancies. Cases B001-B046 are the original regression anchors;
cases B047-B212 add explicit `adapter`, `stratum`, `provenance` and `rationale` tags in the notes
field. The supplementary set is curated and synthetic: it tests deterministic product policy and
parser-normalized fields, rather than claiming to estimate the distribution of the live job market.

## Coverage

- All ten configured adapters are represented by supplementary cases.
- Positive cases cover general security, SOC/detection, DFIR, threat intelligence, application and
  product security, cloud/DevSecOps, vulnerability/offensive security, IAM, GRC, cryptography,
  network/endpoint, OT/ICS and automotive security.
- Seniority cases cover every configured exclusion and explicit internship, graduate, junior,
  trainee, apprentice, working-student and thesis markers.
- Geography cases cover target countries, aliases, country codes, EU region labels, known excluded
  countries, unknown locations and remote ambiguity.
- Negative cases cover generic software roles, vendor boilerplate, physical security, safety,
  non-cyber functions and contextual acronym hard negatives.

The automated suite enforces a minimum of 200 cases, preservation of B001-B046, complete metadata
for the supplementary set, all ten adapters and at least 20 strata.

## Baseline result before rule improvements

The initial 200-case expanded baseline passed the 95% gate: cyber 98.0%, seniority 98.0%, geography
100.0% and final decision 99.5%. After filtering improvements and twelve new regression cases, the
212-case result is cyber 100.0%, seniority 98.1%, geography 100.0% and final decision 100.0%.
