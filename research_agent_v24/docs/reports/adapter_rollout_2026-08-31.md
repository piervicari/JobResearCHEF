# Adapter and cohort rollout evidence

- Date: 2026-08-31
- Operator timezone: Europe/Rome
- Registry: 510 active, deduplicated portal URLs
- Runtime policy: one concurrent request per host, at least one second between host starts, bounded
  retries/redirects/body/run duration, automatic pre-scan backup and post-fetch gate

## Offline gates

| Check | Result |
|---|---|
| Full test suite | PASS, 121 tests |
| Ruff | PASS |
| Master v1.5 acceptance | PASS, all six frozen metrics |
| Taxonomy benchmark | PASS, 46 cases; final accuracy 100% |

Fixtures under `tests/fixtures/` are minimized and sanitized extracts of the named public response
families captured on 2026-08-31. They contain no cookies, credentials or personal contact details.
They prove parser contracts, not permanent third-party availability.

## Structured adapter canaries

| Final run | Portal | Adapter | Requests | Jobs | Complete | Retry / errors | Processing result |
|---:|---|---|---:|---:|:---:|---|---|
| 8 | Ferrari, portal 203 | SuccessFactors RMK | 1 | 7 | Yes | 0 / 0 | 7 excluded, 0 closed |
| 10 | Proofpoint, portal 265 | Workday | 8 | 134 | Yes | 0 / 0 | 134 excluded, 0 closed |
| 11 | PwC Italy, portal 173 | Phenom | 36 | 344 | Yes | 0 / 0 | 343 excluded, 1 review, 0 closed |
| 12 | Oracle Candidate Experience, portal 155 | Oracle Recruiting Cloud | 9 | 196 | Yes | 0 / 0 | 195 excluded, 1 review, 0 closed |
| 14 | MetLife, portal 425 | Avature | 93 | 551 | No | 0 / 0 | 548 excluded, 3 review, 0 closed |

The initial SuccessFactors, Workday and Avature probes exposed real response-shape edge cases. Each
probe remained incomplete or failed locally, lifecycle changes were either safe or gate-blocked, and
the parser was corrected with a regression fixture before the final canary. MetLife declared 556
results but exposed five cards without a title; those records were not invented, so run 14 remained
an incomplete snapshot and could not close vacancies.

The audited registry labels called several portals “Taleo”, but runtime evidence showed Cisco using
Phenom, Siemens and MetLife using Avature, Mercedes using a separate proprietary API and PayPal
returning an anti-bot challenge. Routing was changed only for the verified Phenom/Avature cases; no
generic Taleo adapter or protection bypass was introduced.

## Progressive generic fallback rollout

The cohorts were disjoint, selected in stable host/normalized-URL order from portals routed to the
conservative HTML fallback. Structured canaries were excluded to avoid repeated high-page-count
requests.

| Run | Cohort | Success | Failure | Requests | Retry | 429 | Gate | Processing |
|---:|---:|---:|---:|---:|---:|---:|:---:|---|
| 15 | 25 | 22 | 3 | 51 | 0 | 0 | FAIL, 12% | Skipped |
| 16 | 25 retry after parser fix | 23 | 2 | 51 | 0 | 0 | PASS, 8% | 26 observations, 0 closed |
| 17 | 50 | 40 | 10 | 104 | 0 | 0 | FAIL, 20% | Skipped |

Run 15 found one tool defect: an HTML anchor with a present but valueless `href` raised an
`AttributeError`. The parser now treats it as an empty link and a fixture covers the case. The two
remaining run-16 failures were one denied `robots.txt` and one unresolved DNS name.

Run 17 failures were three unresolved DNS names, one 404 registry URL, two denied `robots.txt`
responses and four HTTP 403/challenge responses. These are coverage/registry issues rather than a
reason to weaken controls. The 100-portal cohort and `--all` scan were not executed because the gate
requires rollout to stop.

## Browser evaluation

None of the rollout failures demonstrated a legitimate need to execute client-side JavaScript.
Playwright would not repair stale DNS/URLs and must not be used to evade robots, 403 or anti-bot
controls. ADR 0008 therefore rejects a runtime browser fallback and the optional dependency was
removed.

## Residual risks

- 398 portals still rely on incomplete HTML discovery; this does not establish complete coverage.
- Registry URL corrections require a versioned source-resolution workflow rather than in-place
  mutation of master v1.5.
- DNS is validated before requests but not pinned through the connection, as described in ADR 0007.
- Automatic backups are intentionally not pruned; operators must monitor disk use and retain/delete
  old backups under an explicit local retention decision.
- The workspace has no Git `HEAD` and all files are currently untracked, so filesystem backups are
  the only rollback mechanism until an initial reviewed commit is created.
