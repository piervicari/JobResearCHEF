# ATS validation — Oracle Recruiting Cloud — 2026-09-08

## Implementation

- Adapter `sources/ats/oracle.py`, registered name `oracle_recruiting_cloud`.
- Catalog: landing page → `recruitingCEJobRequisitions?finder=findReqs;
  siteNumber=<CX>,limit=200,offset=<n>` + secondaryLocations expand.
- Pagination: total-driven adaptive (offset+=received, empty-before-total
  fails, total-change → incomplete snapshot, silent-cap tolerated).
- Detail: ById endpoint via Phase-3 selective detail (same-host).
- Prior evidence: W2 limit200 probe (Honeywell 1361 total / 200 rows);
  CAN2 (catalog 2 wires + live ById detail 0→4273 chars + identity lineage).

## Tenants (3 independent, same adapter/protocol)

1. Honeywell — portal 158, `ibqbjb.fa.ocs.oraclecloud.com`, site CX_1 (US).
   CAN2: 2 wires, 10 jobs, live detail, identity unchanged. (Prior evidence.)
2. Danske Bank — portal 141, branded `danskebank.com/careers/apply` →
   `ejqi.fa.ocs.oraclecloud.eu`, site CX_1001 (EU). This wave: dry-run gate,
   then 3 wires (branded link + landing + API, all 200, retries 0),
   10 jobs persisted (e.g. Acquisition Manager, STOCKHOLM, req 23100).
3. hdep — portal 155, `hdep.fa.us2.oraclecloud.com` direct fa host, site CX
   (US). This wave: dry-run gate, then 2 wires (both 200, retries 0),
   10 jobs persisted (e.g. Operations Administrator, Frankfurt, req 8606,
   empty catalog description — selective-detail shaped, consistent).

## Catalog / pagination / content

- All three: JOBS_FOUND, bounded single page (pilot max_pages=1 — protocol
  check, NOT full-traversal proof). No skips/dups observed within pages;
  per-tenant native IDs stable (23100, 8606, 149413 samples).
- Content spot-check per tenant: title + location + native ID + description
  length present in DB. No AI used for any decision (validation-only scans).
- Detail: no new live detail this wave (§13 max 1, used 0); ById evidence
  stands from Honeywell CAN2. No catalog scan fired any automatic detail (N+1 rule holds).

## Safety

- Per tenant: 1 portal, concurrency 1, retries 0, 10s-class pacing, ≤3 wires
  (3 + 2 actual). No 403/429/challenge/auth-wall. No browser/proxy/rotation.
- Disposable pilot DB only (fresh `prepare-pilot-db --replace`, 0/0 start).
- Career-site total this wave: 5 wires. LLM: 0 (AI frozen).

## Defects

- None new. (The `oracle` vs `oracle_recruiting_cloud` detail-key defect was
  found and fixed during CAN2 with regression test; all three tenants'
  rows carry the production name and select correctly by construction.)

## Gaps (honest, blocking production support)

- No full-catalog traversal live (bounded pages only).
- No empty-board observation on Oracle.
- No multi-page/total-variation episode observed live (guards unit-tested).

## Final status

`VALIDATED_ONE_TENANT → MULTI_TENANT_VALIDATED` (3 tenants).
NOT promoted to PRODUCTION_SUPPORTED: full-traversal + empty-board evidence
missing (see gaps). No code changes this wave.
