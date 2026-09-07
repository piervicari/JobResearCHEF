# ATS Reuse Wave 1.1 — protocol micro-probes + integration (CURRENT)

Supersedes `ATS_REUSE_WAVE1.md` for the implementation choice; that file
remains the historical record of the Wave 1 audit. Decision captured in
`../research_agent_v24/docs/decisions/0060-external-ats-reuse-with-jrc-ownership.md`.

Reference checkouts (frozen, never runtime dependencies):

- ats-scrapers @ `6b44a1b` (2026-09-02, MIT) — `src/ats_scrapers/scrapers/`
- ats-jobs @ `9edd4a6` (2026-08-26, MIT) — `src/providers.js`

## Teamtailor — JSON selected

- RSS live (`polestar.teamtailor.com/jobs.rss`): 200, 27 jobs parsed.
- JSON live (`polestar.teamtailor.com/jobs.json`): 200, 27 items — same
  vacancy set (titles/URLs match), richer bodies.
- Verdict: JSON_SUPERIOR (equivalent catalog, simpler parsing, no XML).
- Selected protocol: `GET https://{tenant}.teamtailor.com/jobs.json`,
  single request, no pagination. Stable ID = numeric ID from public
  `/jobs/{id}-{slug}` URL, `id` field fallback. Description inline
  (`content_html`, raw HTML stored). Empty `items: []` on 200+valid shape
  is a valid empty snapshot; non-2xx (e.g. 404 wrong tenant) never is.
- Production: `TeamtailorAdapter`
  (`research_agent_v24/src/research_agent/sources/ats/teamtailor.py`).
- External provenance: ats-scrapers `scrapers/teamtailor.py` (RSS catalog
  concept, URL-ID rule, shape-guard philosophy) + ats-jobs `providers.js`
  TEAMTAILOR (`jobs.json` feed shape). Rewritten to house guard style;
  no verbatim copy.

## Workable — `?details=true` selected

- Plain widget live (`apply.workable.com/api/v1/widget/accounts/starling-bank`):
  200, 104 rows / 49 unique shortcodes, no usable inline description.
- `?details=true` live (same tenant, one request): 200, same 104 rows /
  same 49 shortcodes / identical fields + full HTML description inline on
  104/104 rows.
- Verdict: INLINE_DETAIL_CONFIRMED — one catalog request replaces 1+49
  detail fetches. No N+1 in scan.
- Selected protocol:
  `GET https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true`,
  single request, no pagination. Identity = shortcode; multi-location rows
  combined with ` | ` (104 rows → 49 vacancies). Empty `jobs: []` is
  ambiguous on this platform (unknown accounts also answer 200+empty):
  completes false with warning, never an authoritative empty snapshot.
- Production: `WorkableAdapter`
  (`research_agent_v24/src/research_agent/sources/ats/workable.py`).
- External provenance: ats-scrapers `scrapers/workable.py` (widget
  endpoint, shortcode identity, multi-location combining, detail concept)
  + ats-jobs `providers.js` WORKABLE (`?details=true` variant). Rewritten
  to house guard style; no verbatim copy.

## BambooHR — pending, NOT integrated

- Live tenants observed returned valid-but-empty boards
  (`blankState` / zero openings); parser correctly yields zero jobs.
- Status: `READY_PENDING_VALIDATION` — integration waits for one observed
  non-empty listing (+1 selective detail), no tenant brute-force.
- Reference (not implemented): `GET https://{slug}.bamboohr.com/jobs/embed2.php`
  catalog + `GET /careers/{id}/detail` JSON detail. ats-jobs `/careers/list`
  is STALE (deprecated 2024 → 404); ats-scrapers async `afetch` fan-out is
  UNSAFE_RUNTIME_PATTERN (reference only).

## Safety evidence (Wave 1.1)

5 wire requests total, sequential, retries 0, concurrency 1, browser 0,
proxy 0, UA rotation 0. HTTP 403: 0. HTTP 429: 0. Challenge: 0.
All probes through the JobResearCHEF HttpFetcher (budgets, pacing,
circuit breaker). Raw bodies + status JSON in `wave1_probes/`.

## Tests

15 new offline tests
(`research_agent_v24/tests/test_teamtailor_workable_adapters.py`, fixtures
are trimmed real wire bodies): fixture parse, shortcode dedup 104→49,
empty/malformed/404 semantics, 403/429 paths, exactly-1-fetch anti-cheat,
registry selection, fetcher-only AST check.

## Verdict

`PASS_EXTERNAL_REUSE_WAVE1` — Teamtailor INTEGRATED, Workable INTEGRATED,
BambooHR READY_PENDING_VALIDATION.
