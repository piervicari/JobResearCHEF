# 0064: Tier-driven frequency, provider-driven scan strategy

- Status: PROPOSED (audit complete, implementation not started)
- Date: 2026-09-09

## Decision

TIER controls WHEN a company is scanned; SOURCE capabilities control HOW.
Tier-S discovery is DAILY and mandatory — never throttled for network reasons.

## Rationale

The 2026-09-09 capability audit (docs/SOURCE_SCAN_STRATEGY.md, 5 live probes)
proves providers differ fundamentally: Greenhouse/Ashby serve the whole
catalog in one request (lightweight variant proven for Greenhouse), while
Workday (page 20, larger rejected) and Eightfold (page 10 fixed) require full
pagination with no safe watermark (ordering unproven everywhere checked).

## Consequences

- Daily discovery per provider strategy (single-shot vs full pagination);
  full traversal accepted where no lossless shortcut exists.
- Provider delta optimizations require live evidence; watermarks default UNSAFE.
- LLM triage runs AFTER identity/delta detection, on cheap metadata only;
  full descriptions via selective detail; NON_CYBER stays lightweight.
- Bounded scans never infer closure (already enforced via complete_snapshot).
- Semantic relevance never controls source discovery (no title hard filters).
