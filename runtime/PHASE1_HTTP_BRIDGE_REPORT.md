# Phase 1 — HTTP bridge report (declarative runtime -> JobResearCHEF transport)

**Date:** 2026-09-06
**Mode:** fully offline (zero live HTTP, zero browser, zero new discovery)
**Frozen files modified:** 0 (`spec_executor.py`, `source_spec.schema.json`,
`job.schema.json`, `sources/mercedes.json`, `sources/nvidia.json` untouched)

## 0. Pre-flight: Cloudflare PASS revoked (offline)

`runtime/candidates/cloudflare.json` declared `paging.strategy=offset`
with `page_param=offset`, i.e. rendered requests of the form
`GET .../jobs?content=true&offset=0`. The captured wire evidence
(`fixtures/cloudflare_catalog_page_raw.json`, 5.5 MB, `meta.total=331`
in a single chunk, fetched with `?content=true` and no paging
parameter) contains zero evidence that the Greenhouse endpoint honours
any server-side paging parameter. The spec asserted protocol behaviour
with no wire evidence: fake offset pagination.

- Archived (preserved): `candidates/_archive/cloudflare.json.PASS_V01_then_revoked`
- New verdict doc: `candidates/cloudflare_NEEDS_EXTENSION.md`
  (`contract_fit=NEEDS_EXTENSION`, missing capability
  `single_request / unpaginated catalog`, `semantic_complete=true`,
  `normalized_text_clean=false` (entity-encoded `content`),
  `authoritative_for_closed` not demonstrated via v0.1)
- Registry: `EXTENSION_PRESSURE_REGISTRY.md` gains the `single_request /
  unpaginated catalog` row (LIVE 1 + HISTORIC_LEGACY 3, MEDIUM_CONFIDENCE_V02)
- `test_candidates_batch3.py` now loads the archived spec (comment +
  path only; no assertion weakened)
- `BATCH3_META_CLOUDFLARE_REPORT.md` carries a superseding banner;
  all other Batch-3 findings stand

Phase-1 PASS set: **Mercedes, NVIDIA, Microsoft**. Cloudflare is
explicitly NOT a Phase-1 success criterion.

## 1. Real JobResearCHEF HTTP contract (read from code, not assumed)

- Class: `research_agent.pipeline.http.HttpFetcher`
  (`JobResearCHEF/research_agent_v24/src/research_agent/pipeline/http.py`)
- Request type: `research_agent.pipeline.http.FetchRequest`, frozen dataclass:
  `FetchRequest(url, headers=None, allow_cache=True, method="GET",
  json_body=None, form_body=None)` — note: **no `query` field**.
- Public method used by every legacy adapter: `await HttpFetcher.fetch(request)`
  -> `FetchResponse` (with `.json()` / `.text`).
- Adapter convention (verified in code): query parameters are folded
  into the URL string by the caller (Radancy/SuccessFactors build URLs
  via urlencode/urlunsplit); POST-JSON bodies go in `json_body` with
  `allow_cache=False` (Workday); form bodies go in `form_body`
  (Google Careers `f.req`).

## 2. New bridge file

`runtime/jobresearchchef_bridge.py` — single public function
`to_fetch_request(rendered, *, fetch_request_cls=None) -> FetchRequest`.
Stdlib only (`copy`); imports no HTTP library at all (no `requests`,
`httpx`, `urllib`, `aiohttp`). The real `FetchRequest` class is
imported lazily from the JobResearCHEF checkout so a missing checkout
fails loudly with `BridgeError` instead of at import time.

Mapping (the whole of it):

| Rendered v0.1 field | FetchRequest field | Rule |
|---|---|---|
| `method` GET/POST | `method` | uppercased; anything else -> `BridgeError` |
| `url` + `query` | `url` | query folded into URL (`?`/`&`), RFC 3986, insertion order; `bool` -> `true`/`false` |
| `headers` | `headers` | copied verbatim; non-`str` value -> `BridgeError` (no coercion) |
| `body` (POST, non-empty object) | `json_body` | deep copy; `form_body` is NEVER produced |
| `body` (GET / empty) | `json_body=None` | non-empty body on GET -> `BridgeError`, same as the fetcher |
| — | `allow_cache` | `True` for GET, `False` for POST (adapter precedent) |

Refusals (all raise `BridgeError`, never silent): unknown method,
missing field, non-http(s) URL, non-dict headers/query/body,
non-string header, `None`/empty-list query value, non-scalar query
value, string/list body (notably: a form-style string is never
converted to `form_body`).

## 3. Per-source results (all through the identical function, zero branches)

| Check | Result |
|---|---|
| Mercedes catalog (POST, exact URL, headers incl. Referer/Origin, `SearchCriteria=[]`, `FirstItem=1`) | PASS |
| NVIDIA catalog (GET, `?domain=nvidia.com&start=0&hl=en`, headers) | PASS |
| NVIDIA detail (GET, interpolated `position_id`, headers) | PASS |
| Microsoft catalog (GET, `?domain=microsoft.com&start=10&hl=en`) | PASS |
| Microsoft detail (GET, interpolated `position_id`) | PASS |
| Source-specific branches in bridge | 0 |
| Source-specific tokens in bridge (static scan incl. comments/docstring) | 0 |
| New HTTP libraries imported by bridge | none (stdlib `copy` only) |
| Fidelity A->B->C (rendered dict == FetchRequest == MockTransport-observed wire incl. POST JSON bytes) | preserved for all three sources |

## 4. Safety: no duplication (mapping table)

All retry/pacing/caching/circuit-breaker behaviour stays in
`HttpFetcher`. The bridge enforces nothing and configures nothing.
Field-by-field translatability for a future Phase-2 harness:

| SourceSpec `safety` field | Existing `HttpFetcher` equivalent | Mappable now? |
|---|---|---|
| `sequential_only: true` | `per_domain_concurrency=1` + `per_domain_min_interval_seconds>0` (serialises starts per host) | YES (constructor args; strict global sequentiality would additionally need `global_concurrency=1`) |
| `min_seconds_between_requests` | `per_domain_min_interval_seconds` | YES, direct |
| `max_requests_per_run` | `max_requests_per_run` (+ `max_requests_per_host_per_run` as host-scoped sibling) | YES, direct |
| `abort_on_http_403` / `abort_on_http_429` | built-in circuit breaker: statuses `{401,403,429}` -> host blocked (`HostCircuitOpenError`), always on | YES (semantics covered; not per-spec opt-out — fetcher is stricter) |
| `max_retries_on_5xx: 1` | `max_retries` over statuses `{500,502,503,504}` (429 is NOT retried: see correction below) | PARTIAL (count maps; retryable set is fetcher-defined, not per-spec) |
| `long_pause_every_n_requests` / `long_pause_seconds` | none (limiter has fixed interval + jitter, no periodic long pause) | NO — harness-level concern, not fetcher |
| `max_consecutive_errors` | none (fetcher blocks host permanently on 401/403/429 instead of counting) | NO — different philosophy; harness-level |
| (spec has no timeout field) | `request_timeout_seconds=20.0` | NO counterpart in spec — fetcher default applies |

Duplicated retry logic: no. Duplicated rate-limit logic: no.
Duplicated circuit-breaker logic: no. Duplicated cache logic: no.

> **CORRECTION (Phase 2, §5 — code re-read, zero behavior change):**
> this report previously stated the fetcher "also retries 429". That is
> wrong. In `HttpFetcher.fetch`, an HTTP 429 raises `HostCircuitOpenError`
> IMMEDIATELY (explicit branch before the retryable-status check), so a
> 429 is never retried — the host circuit opens on the first 429 and the
> cooldown machinery owns recovery. `RETRYABLE_STATUSES` nominally lists
> 429, but the earlier explicit branch makes that entry unreachable for
> 429 responses. For HTTP 403 the fetcher records/blocks the host and
> still returns the response; the adapter (`require_success`, reused by
> `DeclarativeSourceAdapter`) rejects it via the normal ATS failure path
> (`AdapterHttpError` → scanner FAILED, no custom retry/recovery/UA or
> endpoint changes). Pinned by `test_http_429_opens_circuit_without_retry`
> and `test_http_403_uses_the_standard_failure_path` in
> `tests/test_declarative_adapter.py`.

## 5. Test summary

| Suite | Result |
|---|---|
| Bridge tests `runtime/test_jobresearchchef_bridge.py` (22: 5 source + 3 wire-fidelity via real HttpFetcher/MockTransport + 2 static + 2 immutability + 10 error/encoding) | 22 PASS |
| Runtime frozen `test_spec_executor.py` | 42 PASS |
| Runtime `test_candidates_batch1.py` | 24 PASS |
| Runtime `test_candidates_batch2_revised.py` | 29 PASS |
| Runtime `test_candidates_batch3.py` (Cloudflare via archived spec) | 26 PASS |
| JobResearCHEF `test_http_scanner.py` + `test_http_security.py` | 20 PASS |
| JobResearCHEF `test_ats_adapters.py` + `test_google_careers_adapter.py` + `test_greenhouse_bulk_catalog.py` + `test_generic_adapter.py` | 32 PASS |
| No existing test modified to make the bridge pass (only change: Cloudflare spec path -> archive, ordered pre-flight correction) | confirmed |

Bridge tests run under the JobResearCHEF venv so the REAL
`FetchRequest`/`HttpFetcher` classes are exercised:
`PYTHONPATH=<jr>/research_agent_v24/src <jr>/research_agent_v24/.venv/bin/python
test_jobresearchchef_bridge.py`. Live HTTP: 0 (all wire assertions go
through `httpx.MockTransport` with `resolve_dns=False`).

## 6. Packaging note (Phase-2 guidance, NOT implemented)

Phase 1 links the two trees temporarily via `sys.path` (bridge test
inserts `<repo>/JobResearCHEF/research_agent_v24/src` when present).
For Phase 2 the recommended packaging is: publish the declarative
runtime (`spec_executor.py` + `jobresearchchef_bridge.py` + schemas)
as a versioned dependency (or vendored directory) inside JobResearCHEF,
and have `DeclarativeSourceAdapter` import it from there — never copy
`spec_executor.py` (single source of truth stays in `runtime/` until
the monorepo decision lands). No package/complexity added in Phase 1.

## 7. Integrity

- `spec_executor.py`, `source_spec.schema.json`, `job.schema.json`,
  `sources/mercedes.json`, `sources/nvidia.json`: unmodified (mtime
...[truncated]
