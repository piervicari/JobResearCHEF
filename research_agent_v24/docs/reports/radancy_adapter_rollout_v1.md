# Radancy/TalentBrew adapter rollout

Date: 2026-08-31

## Selection

The complete fallback ranking contains 358 current scannable portals and scores employer value,
likely junior/cyber yield, shared-family leverage and observed public-contract evidence. It is stored
in `fallback_adapter_priority_v1.csv`; the ranking command is offline and does not change routing.

Inspection of official responses already collected by bounded scans found a shared
Radancy/TalentBrew server-rendered contract: `#search-results`, explicit total/page metadata and job
cards with public IDs and links. Routing is restricted to seven reviewed hosts and search-result
paths; a matching label or another site on the same host is insufficient.

## Verification

- Sanitized two-page fixture covers pagination, duplicate links, locations and employment type.
- Tests cover verified-host/path routing and the shared per-portal page budget.
- Run 28 canary: BlackRock and Palo Alto Networks, 2/2 success, 40 requests, zero retry/`429`, gate
  PASS. Both were safely incomplete at the original 20-page cap.
- The page cap was aligned to the existing 30-request host budget. Run 29 then scanned BlackRock:
  261 jobs over 27 pages, snapshot complete, zero retry/`429`, gate PASS.
- Palo Alto Networks remains incomplete because its 1,300+ postings exceed the cap; no completeness
  claim or closure permission was introduced.

## Coverage delta

Seven portals move from conservative HTML fallback to the structured adapter. Current scannable
routing is 119 structured portals and 358 incomplete fallbacks. Complete lifecycle coverage improves
for BlackRock, while larger boards remain explicitly incomplete.
