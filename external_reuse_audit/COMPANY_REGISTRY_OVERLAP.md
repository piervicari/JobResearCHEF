# Company Registry Overlap (offline, conservative)

Our dataset: `JobResearCHEF/research_agent_v24/
master_company_universe_v1_5_portal_resolution_wave5.csv` — **12,503 companies**.
External: ats-scrapers `ats-companies/*.csv` (80,390 rows, 47 files, HEAD
2026-09-02) + jobseek `companies.csv` (5,672) / `boards.csv` (7,034).

Method (reproducible, local files only): normalize URLs (lowercase,
strip www, trailing slash) and names (alphanumeric lowercase).
HIGH = our resolved portal URL equals an ats-scrapers board URL, OR our
corporate-website domain equals a jobseek company website domain.
CANDIDATE = normalized-name equality only. No fuzzy matching, no bindings
created. (Vendor paths assume `external_reuse_audit/vendor/` checkouts.)

## Totals

| Class | Count | % |
|---|---|---|
| EXACT/HIGH | 740 | 5.9% |
| CANDIDATE | 792 | 6.3% |
| NO MATCH | 10,971 | 87.7% |

HIGH split: ats-scrapers-only 52, jobseek-only 592, both 96.
Unresolved portals in our set: 12,361, of which 679 (5.5%) have an external hit.

## Per-provider matched companies (HIGH, via ats-scrapers board URL)

| ATS | Matched companies |
|---|---|
| successfactors | 108 |
| workday | 11 |
| greenhouse | 11 |
| phenom | 8 |
| oracle | 5 |
| lever | 2 |
| recruitee | 1 |
| ashby | 1 |
| eightfold | 1 |

(Remainder of HIGH matches resolve via jobseek website-domain equality;
their boards then supply ATS type + token, e.g. `workday/{company,
wd_instance, site}`.)

## Reading guidance

- HIGH rows are seed CANDIDATES with provenance
  (`source, commit SHA, ATS file, original slug/url`), never bindings.
- CANDIDATE rows need future single-probe validation before any use.
- Low coverage is structural (Australia-centric universe vs US/EU-tech
  registries), not a matching bug — hence YES_MODERATE_IMPACT, not HIGH.
