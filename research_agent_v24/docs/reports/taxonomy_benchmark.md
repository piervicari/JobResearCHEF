# Taxonomy benchmark

- Result: **PASS**
- Generated at: `2026-08-31T20:20:58.846301+00:00`
- Dataset: `/Users/pierfrancescovicari/Documents/research_agent/data/benchmarks/taxonomy_v1.csv`
- Cases: 212

| Dimension | Correct | Accuracy | INCLUDE precision | INCLUDE recall |
|---|---:|---:|---:|---:|
| cyber | 212/212 | 100.0% | 100.0% | 100.0% |
| seniority | 208/212 | 98.1% | 100.0% | 97.8% |
| geography | 212/212 | 100.0% | 100.0% | 100.0% |
| final | 212/212 | 100.0% | 100.0% | 100.0% |

Component accuracy gate: 95.0%
Final accuracy gate: 95.0%

## Mismatches

| Case | Dimension | Expected | Actual |
|---|---|---|---|
| B020 | seniority | INCLUDE | EXCLUDE |
| B168 | seniority | INCLUDE | EXCLUDE |
| B179 | seniority | INCLUDE | EXCLUDE |
| B180 | seniority | INCLUDE | EXCLUDE |
