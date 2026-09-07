# Phase-2 hardening report (offline: precedence, preflight, boundary, language)

**Date:** 2026-09-06
**Reviewed commit:** `abf14bb3fb495bf1feb590b17d70b235a79de317`
**Mode:** fully offline (zero live HTTP, zero browser, zero new discovery)
**ADR:** `docs/decisions/0055-phase2-hardening-precedence-preflight-boundary.md`
**Untouched per plan:** AI requeue, detail enrichment, N+1 hydration, DB
schema, v0.2, page_number, bootstrap, cookies, Cloudflare single-request,
Amazon multi-field extraction, Hermes discovery, Telegram, scheduler.

## 1. Registry precedence (§1)

Finding confirmed on real code: `SuccessFactorsRmkAdapter.supports`
matches any target whose `ats_families` contains the marker substring
(URL-independent), and `AdapterRegistry.select` is first-match — with
declarative adapters appended last, a bound portal carrying such a
marker lost to the heuristic. Fix: `structured_adapter_registry()`
places `declarative_adapters` FIRST when provided; no-arg call
byte-identical (pinned name-tuple test). No company-specific branching.

## 2. Safety preflight (§2, §2A, §2B)

Finding confirmed: `scan()` never reads `spec["safety"]` (pinned by
test); `scan_portals()` builds one HttpFetcher from global
ScannerSettings. No second engine was created. New pure module
`sources/declarative/safety.py` (+ `adapter.preflight()` convenience):

| Spec requirement | Class | Rule |
|---|---|---|
| `sequential_only` | CAN_VALIDATE_AGAINST_GLOBAL_SETTINGS | per_domain_concurrency == 1 |
| `min_seconds_between_requests` | CAN_VALIDATE_AGAINST_GLOBAL_SETTINGS | interval >= value |
| `max_requests_per_run` | CAN_VALIDATE_AGAINST_GLOBAL_SETTINGS | scanner budget <= spec budget |
| `abort_on_http_403` | ENFORCED_BY_EXISTING_FETCHER | 403 always in circuit set |
| `abort_on_http_429` | ENFORCED_BY_EXISTING_FETCHER | immediate HostCircuitOpenError, never retried |
| `max_retries_on_5xx` | CAN_VALIDATE_AGAINST_GLOBAL_SETTINGS | max_retries <= value (fetcher set = 5xx + transport errors, 429 excluded) |
| `long_pause_every_n_requests` / `long_pause_seconds` | NOT_CURRENTLY_SUPPORTED | active value → UNSUPPORTED (Mercedes blocked) |
| `max_consecutive_errors` | NOT_CURRENTLY_SUPPORTED | active value → UNSUPPORTED (all three specs carry 8) |

Honest outcome: with current code NO declarative source is
live-runnable (preflight fails closed); offline scans unaffected. No
bypass flag exists. Tests prove a spec stricter than settings cannot
start silently (TOO_PERMISSIVE on default settings' max_retries=2 vs
spec max 1; UNSUPPORTED on Mercedes long pauses; SAFE_TO_RUN reachable
on a synthetic spec with unsupported fields neutralized).

## 3. Exact-page-boundary completeness (§3)

Finding confirmed: the adapter probed only under
`items_path_empty_after_total`, so NVIDIA/Microsoft boundary catalogs
(total=20/10) fetched full pages and still reported incomplete.
Generic fix (no Eightfold code): conditional terminal probe when
`last_page_shorter_than_page_size` is declared AND the last data page
came back full; plus evaluator `>=` sighting of a probe sitting
exactly AT total, plus conservative incomplete when a page returns
items beyond the stated total. Observed request sequences:

- total=12: offsets [0, 10], complete=true, no probe
- total=20: offsets [0, 10, 20(probe empty)], complete=true
- total=10: offsets [0, 10(probe empty)], complete=true

Regression tests: NVIDIA-style ×3 plus a generic synthetic spec
(page_size=5, total=10 → [0, 5, 10], complete).

## 4. Language (§4)

347 real Mercedes items inspected (`mb/all_jobs_full.json` 114,
`all_jobs_full2.json` 119, `all_jobs_raw.json` 114): language codes
observed = only `PublicationLanguage` Code "1" (or absent); duplicate
PositionID count = 0; cross-language duplicate count = 0. No runtime
code reads `preferred_language_codes`. Status:
DECLARED_BUT_UNEXERCISED (schema field kept for compatibility, not
claimed as behavior). Both Mercedes spec copies' notes corrected
(identical text) to stop claiming "collapses to English". No dedup
engine implemented, per plan.

## 5. Traversal invariant (§5)

Pinned by `test_traversal_completeness_ignores_unique_job_count`
(20 traversed items incl. 10 repeated stable IDs → 20 RawJobs kept,
history counts items, complete=true) and documented in adapter README:
catalog traversal completeness != downstream unique-job count.

## 6. Archive / packaging note (§6)

Canonical source is `research_agent/sources/declarative/`; the two
`runtime/` symlinks are intentional and stay. Consequence: an archive
containing only `runtime/` is NOT standalone (symlinks resolve into
JobResearCHEF). No canonical files were duplicated to fix this.
Future handover recommendation: (1) repository commit SHA
(`abf14bb3fb495bf1feb590b17d70b235a79de317` for this review),
(2) runtime artifacts (fixtures, specs, reports, tests),
(3) restore instructions = check out the SHA and keep the
`runtime/` ↔ `JobResearCHEF/` relative layout (symlinks are relative
and survive relocation of the repo root as a whole).

## Integrity

- SourceSpec capability additions: 0 (strategy still const offset)
- DB migrations: 0; RawJob/SourceJob/CanonicalJob unchanged
- Source-specific branches: 0 (static scans green on all three core files)
- Live HTTP requests: 0; browser calls: 0
- Tracked edits: `sources/ats/registry.py` (order),
  `sources/declarative/{adapter,executor,README}.py/md`,
  Mercedes notes ×2 (identical), `PHASE1_HTTP_BRIDGE_REPORT.md`
  (§5 correction stands); new: `safety.py`, ADR 0055, this report
