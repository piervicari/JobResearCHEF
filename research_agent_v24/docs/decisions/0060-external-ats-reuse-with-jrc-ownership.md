# Decision 0060: External ATS implementations reused as protocol/parser references

- Status: ACCEPTED
- Date: 2026-09-06

## Decision

External ATS implementations are reused as protocol/parser references while
JobResearCHEF retains network and lifecycle ownership:

- Teamtailor: `GET {tenant}.teamtailor.com/jobs.json` (JSON selected over
  RSS after live comparison: same 27 vacancies, richer bodies, simpler
  parsing). New `TeamtailorAdapter` (~150 LOC), single-request catalog,
  inline HTML description, numeric-ID-from-URL with id fallback.
- Workable: `GET apply.workable.com/api/v1/widget/accounts/{slug}?details=true`
  (INLINE_DETAIL_CONFIRMED live: 104/104 rows with full description — one
  request replaces 1+49). New `WorkableAdapter` (~190 LOC), shortcode
  identity with multi-location combining (104 rows → 49 vacancies).
- BambooHR: NOT integrated (`READY_PENDING_NONEMPTY_LIVE_VALIDATION`) —
  valid tenants observed but only empty boards live; parsing proven offline
  only via upstream fixtures.
- Rejected: ats-jobs `fetchCompany(domain)` fan-out runtime; ats-scrapers
  async/proxy/browser runtimes; ats-jobs stale BambooHR `/careers/list`;
  fake-offset SourceSpec simulation for single-request catalogs
  (Cloudflare precedent holds — no v0.2 built for elegance).

## Why

Wave 1.1 micro-probes (5 wire requests, sequential, zero 403/429/challenge)
proved the exact wire shapes on verified tenants. Both catalogs are single
GET → full catalog → no pagination, which v0.1 (frozen, offset-based)
cannot express without fake pagination — so small house-style adapters
(~340 LOC total, Greenhouse-shaped: strict shape guards, job cap, honest
empty semantics) beat a v0.2 `single_request` capability on complexity
today. That capability would cover Cloudflare + Workable + Teamtailor and
is recorded as future work, not built.

## Detail model

No automatic N+1 in any catalog scan (anti-cheat tested: exactly 1 fetch).
Teamtailor/Workable-details carry descriptions inline. BambooHR detail
(`careers/{id}/detail` JSON) stays future selective hydration, same as all
declarative detail.

## Safety constraints

HttpFetcher only (no direct httpx/requests/aiohttp/browser/proxy/retry in
adapters — AST-tested). 404 wrong tenant → AdapterHttpError, never an
authoritative empty snapshot. Workable `jobs: []` → complete=false with
warning (unknown accounts also answer 200+empty). Teamtailor `items: []`
on 200+valid shape → valid empty snapshot. Global/per-host budgets,
403/429, pacing, circuit breaker unchanged and authoritative.

## License/provenance

- ats-scrapers @ 6b44a1b, MIT © Kalil Bouzigues: `scrapers/teamtailor.py`
  (RSS catalog concept, URL-ID rule, shape-guard philosophy),
  `scrapers/workable.py` (widget endpoint, shortcode identity,
  multi-location combining, Markdown-detail concept).
- ats-jobs @ 9edd4a6, MIT: `src/providers.js` TEAMTAILOR (`jobs.json`
  feed shape), WORKABLE (`?details=true` variant).
- No verbatim code copied (rewritten to house `require_*` guard style);
  endpoint shapes and factual mappings attributed here and in module
  docstrings. No runtime dependency added; no provider discovery executed.

## Current implementation impact

- `sources/ats/teamtailor.py`, `sources/ats/workable.py`: new.
- `sources/ats/registry.py`: both registered in structured + default
  registries (after Avature / before generic fallback).
- `tests/test_teamtailor_workable_adapters.py`: 15 tests; fixtures are
  trimmed real wire bodies (polestar jobs.json ×3, starling-bank widget
  3 shortcodes).
- Pre-existing registry-order test updated for the two new names.

## Open questions

- BambooHR non-empty live validation (needs 1 listing + 1 detail probe).
- `single_request` declarative capability (v0.2+) if a fourth provider
  wants it.
