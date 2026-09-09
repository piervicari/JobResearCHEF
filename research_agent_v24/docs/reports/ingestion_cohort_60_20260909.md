# 60-company ingestion cohort — 2026-09-09

## Baseline

- HEAD `1a7f6d3`, clean tree, `git diff --check` clean. Suite before: 421/0.
- Canonical DB `~/.local/share/research-agent/research_agent.db`
  (hash `ece676dc…`) verified resolved + untouched (re-verified after).
- Legacy DB unused. Disposable cohort DB via normal V25 sync (pilot-copy base
  + current registry CSV): 1 created + 70 reused portals. No manual seeding.

## Membership (frozen pre-traffic, 60 portals)

Two-tier composition (documented): Tier-1 V25 operational portals first;
Tier-2 legacy scan-enabled registry portals for validated families (Oracle
141/145/155/158, Lever 214/215, Greenhouse apiiro/chainguard/etc, Workday
17-family) — all canonical records, none invented. Excluded: Airbus (2000
board, cheaper equivalents), Amex Oracle (wildcard hostname), JPMorgan Oracle
(known SSO wall), NVIDIA Workday (same catalog as Eightfold door).
HIGH 21 (previously live-scanned) / MEDIUM 39. GH at exactly 40% (24/60).
Batches A/B/C assigned round-robin by family (20 each). Two shared-identity
notes: 555 Anduril/Anduril Industries (alias), 384 Alphabet/Mandiant
(parent/brand) — no company scanned twice. No replacements after freeze.

## Execution

Sequential real scanner→adapter→HttpFetcher→gate→persist→disposable DB.
Per-run cap 4 wires / 2 pages, jobs 5000, concurrency 1, retries 0, pacing
2–4 s. Catalog-only, no detail. Checkpoint budgets 60/60/60, global 180.

## Outcomes

SUCCESS_COMPLETE 26, SUCCESS_BOUNDED 24, EMPTY_VALID 5, failed 5.
Successful ingestion 55/60 = 91.7%. HIGH 21/21 = 100%. MEDIUM 34/39.

Workday (18): 16 bounded exact (40/40 each; totals 419–1581 seen, 2-page cap),
2 failed (579/266 site-less bare-host 406 — REGISTRY_FAILURE, shared cause).
Greenhouse (24): 18 complete exact (incl. GitLab 230, Okta 310, Datadog 451,
MongoDB 403), 3 empty-valid, 3 failed (SpaceX/Anduril oversize, SentinelOne 404).
Oracle (3): Danske/EDBZ/Honeywell 400/400/181 bounded or complete exact.
Lever (4): Safe/WatchGuard complete (18/24), Palantir/Sysdig bounded+complete.
Eightfold (2): NVIDIA/Microsoft 20/20 bounded exact.
Ashby (3): OpenAI 780, Vanta 112, Horizon3ai 106 — all complete exact.
SmartRecruiters (5): Visa/ZeroFOX/Booking empty-valid, ServiceNow/Bosch
200/200 bounded exact. Google (1): 40 bounded exact (total churning 3362→3367).
Elastic rerun: transient ReadTimeout → SUCCESS 354 on 1-wire retry.
SentinelOne: board now 404s (REGISTRY_FAILURE — needs re-resolution).

Identity exception (P0, fixed — see Defects): Intel 521 (22× "Spotlight Job")
and Thales 277 (40× "Regular Employee") collapsed native IDs.

## Metrics

- Network: 103 wires total (A 35 / B 33 / C 34 + 1 rerun; budget 180),
  avg 1.7/company; retries 0; 403/429/challenges 0.
- Data: 5969 raw observations → 5969 adapter rows → 5969 persisted rows
  (row-count exact everywhere; native-ID uniqueness broken on 62 rows —
  22× "Spotlight Job" + 40× "Regular Employee" — pre-fix, disposable DB only);
  malformed/skipped 0; all rows PENDING_AI.
- Snapshots: complete 31 (26 + 5 empty), bounded 24, failed 5.

## Failure taxonomy

- REGISTRY 3 (579, 266 site-less URLs; 547 dead board). ROUTING 0. ADAPTER 2
  (521, 277 badge-ID — fixed). UPSTREAM 3 (553, 555 oversize boards; 560
  transient timeout, recovered). PERSISTENCE 0 (as a layer — dup rows were
  the adapter's bad IDs). SAFETY 0 (guards functioned). UNKNOWN 0.

## Defects

- P0 (fixed): Workday `bulletFields[0]`-blind requisition picked badge labels
  on Intel/Thales → duplicate native IDs persisted. Fix: requisition-shape
  regex (JR/R/J/REQ+digits, bare digits; badges never match; externalPath
  fallback), provider-general, no company branches. Regression test added.
  Saved-body replay through the real scan path (0 wires): 40 unique each.
  Full suite green. No live rescan needed (parse-only fix).
- P1: Greenhouse single-response 20 MB ceiling blocks mega-boards (SpaceX,
  Anduril); JPMorgan-class SSO walls; SentinelOne 404 needs re-resolution;
  site-less Workday records need RUN29-style correction.
- P2: none. Fixes: 1. Tests added: 1.

## Verdict

PASS (55/60 ≥ 51, HIGH 100% ≥ 90%, no unresolved P0, budgets respected,
runtime untouched).

## Next

Targeted repair wave for P1s (GH large-board path, registry corrections),
then 50–100 scale. No second cohort executed here.
