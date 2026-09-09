# First 15-company ingestion cohort — 2026-09-09

## Baseline

- HEAD `6d6af32`, clean tree, `git diff --check` clean. Suite before: 421/0.
- Canonical runtime DB `~/.local/share/research-agent/research_agent.db`
  (hash `ece676dc…`, 593 portals / 652 jobs / 16 runs) — verified resolved
  by real config and untouched throughout (hash re-verified after).
- Legacy `data/research_agent.db` not used. No merge. No AI. No browser/proxy.

## Disposable cohort DB (normal V25 path, 0 live wires for setup)

- Pilot-copy of the canonical DB + `sync-tier-s-operational-sources`
  (current `tier_s_operational_sources_v1.csv`, version `tier_s_cohort15`):
  1 created portal (NVIDIA Eightfold), 70 reused, mappings updated.
- No manual portal injection. Bodies saved under `/tmp/cohort15` (not committed).

## Selection (deterministic, frozen before traffic)

Rule: within each family take the lowest portal-ids among TECHNICALLY_VERIFIED
READY_TO_PROBE V25 sources with a working adapter select; exclusions: Airbus
(2000-board, cheaper equivalents exist), Amex Oracle (wildcard hostname —
deliberately broken, never selected), NVIDIA Workday (same catalog as the
Eightfold door). Oracle ended with 1 viable tenant → Other took 4.

| # | Company | source_key | Family | Confidence |
|---|---------|-----------|--------|-----------|
| 1 | CrowdStrike | crowdstrike_workday | Workday | HIGH |
| 2 | Proofpoint | proofpoint_workday | Workday | HIGH |
| 3 | Blue Origin | blueorigin_workday | Workday | HIGH |
| 4 | SecurityScorecard | securityscorecard_greenhouse | Greenhouse | HIGH |
| 5 | Tenable | tenable_greenhouse | Greenhouse | HIGH |
| 6 | Okta | okta_greenhouse | Greenhouse | HIGH |
| 7 | JPMorgan Chase | jpmc_oracle_recruiting_cloud | Oracle | HIGH |
| 8 | Palantir Technologies | palantir_lever | Lever | HIGH |
| 9 | Sysdig | sysdig_lever | Lever | HIGH |
| 10 | NVIDIA | nvidia_eightfold | Eightfold | HIGH |
| 11 | Microsoft | microsoft_custom | Eightfold | HIGH |
| 12 | OpenAI | openai_ashby | Ashby | MEDIUM |
| 13 | Visa | visa_smartrecruiters | SmartRecruiters | MEDIUM |
| 14 | Vanta | vanta_ashby | Ashby | MEDIUM |
| 15 | ServiceNow | servicenow_smartrecruiters | SmartRecruiters | MEDIUM |

Distribution: Workday 3, Greenhouse 3, Oracle 1, Lever 2, Eightfold 2,
Other 4 (Ashby 2, SmartRecruiters 2). HIGH 11, MEDIUM 4.

## Preflight (offline, all 15)

All 15: portal + mapping exist, structured adapter selected (no generic
fallback), no same-catalog duplicates (NVIDIA Eightfold only). All READY.
Membership frozen before traffic; no replacements.

## Execution

Sequential, real scanner→adapter→HttpFetcher→gate→persist→disposable DB.
Per-run cap 4 wires / 2 pages, jobs cap 5000, concurrency 1, retries 0,
3 s pacing. Catalog-only (no detail requests).

## Outcomes (raw=adapter=persisted=unique exact on all 15, verified offline)

- CrowdStrike (Workday): SUCCESS_BOUNDED, 3 wires, 40/40/40, complete FALSE
  (total 419, 2-page cap). Sample: R29998 Program Manager III (USA Remote).
- Proofpoint (Workday): SUCCESS_BOUNDED, 3 wires, 40/40/40, FALSE (total 146).
- Blue Origin (Workday): SUCCESS_BOUNDED, 3 wires, 40/40/40, FALSE (total 1581).
- SecurityScorecard (Greenhouse): SUCCESS_COMPLETE, 1 wire, 40/40/40, TRUE.
- Tenable (Greenhouse): SUCCESS_COMPLETE, 1 wire, 39/39/39, TRUE.
- Okta (Greenhouse): SUCCESS_COMPLETE, 1 wire, 310/310/310, TRUE.
- JPMorgan Chase (Oracle): UPSTREAM_BLOCKED, 4 wires (302→301→302→SSO login),
  0 rows. Oracle Access Management login wall — no bypass attempted, no rerun.
- Palantir (Lever): SUCCESS_BOUNDED, 2 wires, 200/200/200, FALSE (2-page cap).
- Sysdig (Lever): SUCCESS_COMPLETE, 1 wire, 14/14/14, TRUE.
- NVIDIA (Eightfold): SUCCESS_BOUNDED, 2 wires, 20/20/20, FALSE (2-page cap).
- Microsoft (Eightfold): SUCCESS_BOUNDED, 2 wires, 20/20/20, FALSE (2-page cap).
- OpenAI (Ashby): SUCCESS_COMPLETE, 1 wire, 781/781/781, TRUE.
- Visa (SmartRecruiters): EMPTY_VALID, 1 wire, 0/0/0, TRUE (zero active jobs).
- Vanta (Ashby): SUCCESS_COMPLETE, 1 wire, 112/112/112, TRUE.
- ServiceNow (SmartRecruiters): SUCCESS_BOUNDED, 2 wires, 200/200/200, FALSE
  (2-page cap).

## Metrics

- Selected 15, preflight-ready 15, attempted 15.
- SUCCESS_COMPLETE 6, SUCCESS_BOUNDED 7, EMPTY_VALID 1, UPSTREAM_BLOCKED 1.
- Successful ingestion 14/15 = 93.3%. HIGH 10/11, MEDIUM 4/4.
- Family: Workday 3/3 bounded; Greenhouse 3/3 complete; Oracle 0/1;
  Lever 1 complete + 1 bounded; Eightfold 2/2 bounded; Ashby 2/2 complete;
  SmartRecruiters 1 empty-valid + 1 bounded.
- Network: 28 wires total (budget 45), avg 1.87/company; retries 0;
  403/429/challenges 0 (JPMorgan met 302→SSO, counted as upstream auth wall).
- Data: 1856 raw observations → 1856 unique native IDs → 1856 persisted rows;
  duplicates 0 beyond dedup-by-design; malformed/skipped 0; mismatches 0.
- Snapshots: complete 7 (6 + 1 empty), bounded-incomplete 7, failed 1.
- All rows PENDING_AI (no AI processing).

## Failure taxonomy / defects

- REGISTRY/ROUTING/PERSISTENCE/SAFETY: 0. ADAPTER: 0. UPSTREAM: 1 (JPMorgan SSO).
- P0: none. P1: JPMorgan Oracle SSO wall (tenant-specific; Oracle adapter
  proven on 3 other tenants; alternative Oracle tenants exist). P2: none.
- Fixes: none. Tests added: none (no product defect).

## Verdict

PASS (14/15 ≥ 12, no P0, exact accounting, untouched runtime, budget respected).

## Next

Targeted note: retry JPMorgan only if an SSO-free Oracle tenant path emerges
(no bypass); otherwise proceed to 50–100 when operators judge the SSO tenant
acceptable to exclude. No second cohort executed here.
