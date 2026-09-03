# Progressive scan scale validation

Date: 2026-08-31

## Outcome

The corrected 50-portal and 100-portal cohorts pass the release gate. The final representative run
covered all ten configured adapters, stayed below the new request budgets and produced no `429`,
retry storm or unexpected complete empty snapshot.

| Run | Purpose | Success | Failure | Requests | Retries | `429` | Jobs | Gate |
|---:|---|---:|---:|---:|---:|---:|---:|---|
| 17 | Original cohort 50 | 40 | 10 | 104 | 0 | 0 | 169 | FAIL |
| 22 | Corrected cohort 50 | 47 | 3 | 117 | 3 | 0 | 297 | PASS |
| 23 | Initial cohort 100 | 73 | 27 | 580 | 2 | 1 | 4,216 | FAIL |
| 24 | Adapter/route remediation canary | 7 | 3 | 95 | 1 | 0 | 1,420 | FAIL |
| 25 | Corrected canary | 8 | 0 | 91 | 0 | 0 | 1,445 | PASS |
| 26 | Corrected representative cohort 100 | 92 | 8 | 360 | 0 | 0 | 3,333 | PASS |

Run 26 failure rate was 8%, retry rate 0%, and the post-fetch pipeline completed. It created 13
canonical jobs, updated 11, identified 14 duplicate observations and closed one canonical job only
through the existing lifecycle rules.

## Changes made after the failed scale run

- Initially capped each portal at 20 pages and 500 observed jobs, each host at 30 requests and each run at 500
  requests. Capped snapshots are explicitly incomplete and therefore cannot close jobs.
- Made paginated adapters enforce the shared limits. A malformed Workday posting no longer aborts an
  otherwise usable portal, while Phenom supports the observed server-rendered TalentBrew contract.
- Distinguished a source-confirmed empty board from an unexpected parser empty result.
- Extended challenge detection to known Radware/perfdrive endpoints.
- Corrected, retired or suspended affected routes through immutable registry artifacts and retained
  the previous mappings and scan evidence.

After scale validation, the page cap was raised from 20 to 30 while preserving the 30-request host
budget. This allowed the verified Radancy adapter to prove BlackRock complete in 27 pages; larger
boards still stop incomplete.

## Residual failures and disposition

Run 26 failures were one redirect loop, one robots denial and six HTTP access challenges. Orca
Security, Orsted, Parker Hannifin, Pentera, General Motors, Shield AI, Torq and Vantage Data Centers
were suspended by `registry_corrections_run26_v1.csv`. No bypass, proxy, browser fallback or repeated
access attempt was introduced.

After the correction, 477 portals are currently scannable: 112 structured routes and 365
conservative official-HTML fallbacks.

## Gate conclusion

The progressive rollout gate is accepted. Further live expansion may proceed only with the same
bounded execution, explicit cohort selection and stop rules.
