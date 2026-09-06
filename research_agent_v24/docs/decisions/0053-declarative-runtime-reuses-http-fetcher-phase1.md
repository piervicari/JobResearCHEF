# 0053 — Reuse HttpFetcher as the sole transport for DeclarativeSourceAdapter (Phase 1)

**Status:** Accepted / Phase 1 (offline proof-of-integration, no live traffic)
**Date:** 2026-09-06

## Decision

The declarative `source_spec/v0.1` runtime does NOT get its own HTTP
client. `spec_executor.py` renders plain request dicts
`{method, url, headers, query, body}` (no I/O); a small source-agnostic
bridge (`runtime/jobresearchchef_bridge.py::to_fetch_request`) translates
each rendered dict into the existing
`research_agent.pipeline.http.FetchRequest`, and the existing
`research_agent.pipeline.http.HttpFetcher` performs the request with
its current retry / pacing / circuit-breaker / cache / DNS-validation /
redirect-limit / body-budget behaviour unchanged.

## Why

- The fetcher is mature and already covers every safety concern the
  declarative specs declare (per-domain pacing, 403/429 circuit
  breaker, 5xx retry, per-run budgets, private-network guard).
- A second client would duplicate exactly the logic most likely to
  cause blocks if it ever diverged. One wire path means one place to
  audit before any live run.
- Legacy ATS adapters already speak `FetchRequest`; routing declarative
  specs through the same type makes future `DeclarativeSourceAdapter`
  a sibling in `AdapterRegistry`, not a parallel stack.

## Implementation shape

```text
source_spec/v0.1 JSON
  -> spec_executor.render_catalog_request / render_detail_request  (frozen, no I/O)
    -> jobresearchchef_bridge.to_fetch_request  (pure serializer, stdlib only)
      -> FetchRequest(url with query folded in, headers, method,
                      json_body=<body or None>, allow_cache=<GET only>)
        -> HttpFetcher.fetch  (unchanged: safety, retry, cache, MockTransport in tests)
```

The bridge maps POST bodies to `json_body` only and never produces
`form_body`; anything outside v0.1 (unknown method, non-object body,
body on GET, non-http URL, non-string headers) raises `BridgeError`
instead of guessing. Phase-1 scope is GET + POST-JSON catalog/detail
for the three active PASS specs (Mercedes, NVIDIA, Microsoft).

## Trade-offs / challenges

- Minimal coupling to the `FetchRequest` constructor shape
  (`url, headers, allow_cache, method, json_body, form_body`). If the
  fetcher ever renames a field, the bridge breaks loudly at call time
  (22 offline bridge tests pin the shape), which is preferable to a
  silent drift.
- Query parameters are folded into the URL string because
  `FetchRequest` has no `query` field; percent-encoding is a small
  local RFC 3986 encoder (the bridge deliberately imports no HTTP
  library, not even `urllib`, so the encoding choice is pinned by the
  `test_query_encoding_is_rfc3986` test).
- `HttpFetcher` caching applies to GET only and POSTs run with
  `allow_cache=False`, matching existing adapter precedent
  (Workday/Google-Careers POSTs).
- SourceSpec `safety` fields are NOT enforced by the bridge; the
  report `runtime/PHASE1_HTTP_BRIDGE_REPORT.md` carries the
  field-by-field mapping (directly mappable vs not yet mappable) so a
  Phase-2 harness can translate spec safety into fetcher constructor
  arguments explicitly.

## Current implementation impact

- New: `runtime/jobresearchchef_bridge.py` (~150 lines, stdlib only).
- New: `runtime/test_jobresearchchef_bridge.py` (22 tests, all offline;
  wire-fidelity tests use the real `HttpFetcher` + `httpx.MockTransport`).
- Pre-flight correction (same change): `candidates/cloudflare.json`
  archived to `candidates/_archive/cloudflare.json.PASS_V01_then_revoked`
  (fake unobserved `offset` pagination) with new
  `candidates/cloudflare_NEEDS_EXTENSION.md`; `test_candidates_batch3.py`
  loads the archived spec; `EXTENSION_PRESSURE_REGISTRY.md` gains the
  `single_request / unpaginated catalog` capability row.
- No change to `spec_executor.py`, `source_spec.schema.json`,
  `job.schema.json`, frozen sources, or any JobResearCHEF source file.

## Open questions

- Phase-2 packaging: where should the bridge live permanently
  (vendored copy under JobResearCHEF vs JobResearCHEF vendoring the
  runtime)? Deferred; Phase 1 uses temporary `sys.path` linking.
- Phase-2 safety translation: explicit `safety -> HttpFetcher(...)`
  constructor mapping per spec (table drafted in the Phase-1 report).
- v0.2 `single_request` paging strategy for Greenhouse-family sources
  (first evidence: revoked Cloudflare spec).
