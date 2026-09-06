# 0055 — Phase-2 hardening: precedence, safety preflight, boundary probe (offline)

**Status:** Accepted / hardening (offline, no live traffic)
**Date:** 2026-09-06
**Follows:** 0054 (sibling adapter), 0053 (fetcher reuse)
**Reviewed commit:** `abf14bb3fb495bf1feb590b17d70b235a79de317`

Every finding below was verified against the real code before any
change; nothing here adds a SourceSpec capability, a migration, AI
requeue, detail enrichment, or any item of the explicit NOT-touch list.

## Decisions

1. **Explicit declarative bindings have precedence over heuristic
   legacy adapter matching.** `structured_adapter_registry()` now
   places `declarative_adapters` FIRST when provided
   (`AdapterRegistry.select` is first-match, and e.g.
   `SuccessFactorsRmkAdapter.supports` matches any target carrying the
   family marker regardless of URL — verified in code — so appending
   declarative adapters last let heuristics shadow explicit bindings).
   Unbound portals fall through to legacy adapters in original order;
   the no-argument registry is byte-identical to before (pinned test).

2. **SourceSpec safety requirements may never be silently ignored.**
   Documented CURRENT STATE: `scan()` does not read `spec["safety"]`
   (pinned by a test asserting no safety-section access in `scan`).

3. **Existing HttpFetcher/Scanner remain sole safety owners.** No
   second retry/pacing/circuit-breaker engine was introduced; the
   preflight is a pure comparison function, not an enforcement engine.

4. **Unsupported spec safety requirements fail closed before network
   access.** New `sources/declarative/safety.py`: `preflight_safety`
   returns SAFE_TO_RUN / UNSUPPORTED_SAFETY_REQUIREMENT /
   SCANNER_SETTINGS_TOO_PERMISSIVE; `assert_safe_to_run` raises
   `UnsafeToRunError`; no bypass flag exists anywhere. Honest outcome
   of applying it: `long_pause_*` (Mercedes active) and
   `max_consecutive_errors` (all three specs active) are
   NOT_CURRENTLY_SUPPORTED, so no declarative source is live-runnable
   today — implementing those harness capabilities is scoped future
   work, not adapter work. Mapping per requirement lives in the module
   docstring (ENFORCED_BY_EXISTING_FETCHER: abort_on_403/429;
   CAN_VALIDATE: sequential_only, min_interval, max_requests_per_run,
   max_retries_on_5xx).

5. **Exact-page-boundary completeness may use a conditional terminal
   probe when required by the declared completeness semantics.**
   Specs whose rules REQUIRE the empty page keep the unconditional
   probe; specs whose rules merely ACCEPT it
   (`last_page_shorter_than_page_size`) probe only when the last data
   page came back full (total=12 → stop, no probe; total=20/10 →
   exactly one probe). No Eightfold-specific code. This also fixed the
   evaluator's `>` vs `>=` sighting of a probe sitting exactly AT
   total, plus a conservative incomplete verdict when a page returns
   items beyond the stated total. All generic, all BUGFIX (not v0.2).

6. **`preferred_language_codes` remains unexercised until real fixture
   evidence exists.** 347 real Mercedes items across three artifacts
   (`mb/all_jobs_full.json`, `all_jobs_full2.json`, `all_jobs_raw.json`):
   only `PublicationLanguage` Code 1 (or absent), zero duplicate
   PositionIDs. No runtime code reads the field. Status:
   DECLARED_BUT_UNEXERCISED (kept in schema for compatibility, not
   claimed as behavior). Both Mercedes spec copies' notes corrected to
   stop claiming the runtime "collapses to English". Invariant pinned
   by test and docs: traversal completeness (page history item counts)
   != downstream unique-job count; any future dedup happens downstream
   of that accounting.

## Why

Phase 2 was live-runnable in shape but not in guarantees: a bound
portal could lose to a heuristic, a boundary catalog could never
report complete, and every spec's safety section was decorative. This
hardening closes the three gaps without adding capabilities, and
documents the two remaining honest blockers (long pauses,
consecutive-error budget) instead of silently ignoring them.

## Implementation shape

```text
registry.py:  declarative_adapters spread moved before legacy list
sources/declarative/safety.py:  NEW (EffectiveScannerSafety,
  preflight_safety, assert_safe_to_run, UnsafeToRunError)
sources/declarative/adapter.py:  preflight() convenience; conditional
  probe in _upcoming_offsets; beyond-total-items guard in scan()
sources/declarative/executor.py:  >= fix for probe-at-total sighting
specs ×2:  mercedes.json notes corrected (identical text both copies)
tests/test_declarative_adapter.py:  +14 tests (precedence A/B/C, safety
  ×6, boundary ×4 incl. synthetic spec, traversal invariant ×1)
```

## Trade-offs / challenges

- Precedence-first means a misconfigured binding now shadows legacy
  adapters deterministically rather than losing to them
  non-deterministically-by-order: misconfiguration fails loudly at
  scan time (AdapterSchemaError on malformed spec) instead of silently
  routing elsewhere. Bindings remain operator-owned exact strings.
- The preflight deliberately blocks ALL current declarative sources
  live (unsupported long-pause / consecutive-error requirements).
  This is the intended fail-closed outcome, not a regression: offline
  scans are unaffected, and the blockers are named with their owning
  layer (harness run-control, not transport, not spec).
- The conditional probe adds at most one request per scan, only when a
  declared rule cannot be satisfied otherwise; partial-final-page
  scans issue zero extra requests (asserted offsets in tests).

## Current implementation impact

- Changed: `sources/ats/registry.py` (order), `sources/declarative/`
  (`adapter.py`, `executor.py`, `README.md`), Mercedes notes ×2.
- New: `sources/declarative/safety.py`, 14 hardening tests.
- Unchanged: legacy adapters, Scanner, HttpFetcher, lifecycle, DB
  schema (zero migrations), RawJob/SourceJob shapes, v0.1 capabilities
  (zero additions), AI requeue, detail enrichment (both untouched per plan).

## Open questions (unchanged from 0054, still deferred)

- Persist `source_spec_ref` on Portal; detail-enrichment wiring for
  new/changed/candidate jobs only; v0.2 `single_request` paging;
  harness run-control for long pauses + consecutive-error budget
  (the two preflight blockers); `process_scan_results` AI-requeue gap.
