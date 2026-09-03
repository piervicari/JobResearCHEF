# Decision 0005: Complete cyber job storage with separate AI analysis

- Status: Accepted
- Date: 2026-09-02

## Decision

For every vacancy classified as cybersecurity, persist the complete source job record independently of
seniority. Preserve source truth separately from LLM-derived interpretation.

Do not overwrite raw/source fields with AI-derived values.

## Why

- Senior jobs are research data for future skill/career reverse engineering.
- LLM models, prompts and taxonomies will change; the source record must remain re-analyzable.
- Keeping source truth separate prevents model guesses from becoming indistinguishable from employer data.

## Suggested source job contract

```text
jobs
----
job_id
company_id
company_name
external_job_id        # when ATS/source supplies one
title_raw
location_raw
description_raw
job_url
posted_at              # when supplied
employment_type_raw    # when supplied
source_name
source_payload_json    # optional structured source payload for future-proofing
first_seen_at
last_seen_at
seen_count
content_hash
status
```

"Everything" means retain all useful fields exposed by the source, not only the normalized subset.
`source_payload_json` is a low-cost escape hatch for fields that differ across ATS families.

## Separate AI analysis

```text
job_ai_analysis
---------------
job_id
model
prompt_version
analysis_version
analyzed_at
domains
role_family
specializations
seniority
years_experience_min
years_experience_max
skills_required
skills_preferred
degree_requirement
certifications
```

The schema should begin small. Avoid speculative fields such as prestige score, fit score, salary
prediction or personality unless they become real product requirements.

## Trade-offs / challenges

- Persisting all source data is cheap compared with re-fetching lost history.
- Re-running AI analysis should not duplicate the source job.
- Source-provided facts and inferred classifications must stay distinguishable.
