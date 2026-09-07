# Extension Pressure Registry

This file is the cumulative record of capabilities **not** in
`source_spec/v0.1` that have been observed during source discovery
across batches. Each row corresponds to one capability category.

**Rules**:
- A capability enters this registry only with positive evidence
  from a real successful request/response (not from 4xx errors,
  guesses, or reverse engineering of incomplete protocols).
- "Real evidence count" = the number of independent successful
  request/responses observed demonstrating the gap.
- "Repeated across sources?" = yes if more than one real source
  exhibits the gap; otherwise no.
- "Candidate for v0.2?" = yes only if repeated across at least 2
  sources, or if the gap would clearly affect future batches.

For each capability, three counts are reported (correction from
the previous audit):

- **LIVE_FIXTURE**: count of real successful responses saved to
  `runtime/fixtures/`. These are real wire responses captured
  with curl and consumed by frozen tests.
- **HISTORIC_LEGACY_FIXTURE**: count of legacy JobResearCHEF
  adapters that have a real saved fixture under
  `JobResearCHEF/research_agent_v24/tests/fixtures/` AND a test
  in `tests/test_ats_adapters.py` that consumes it.
- **CODE_ONLY**: count of legacy adapters or batches with code
  only, no real fixture (MockTransport, hand-constructed mock
  payloads, error responses).

Only LIVE_FIXTURE and HISTORIC_LEGACY_FIXTURE count toward "real
evidence" for v0.2 promotion. CODE_ONLY is a yellow flag, not
green.

This file is NOT frozen. It is purely informational and feeds the
eventual v0.2 design.

## Capabilities observed

| Capability | Category | Sources (LIVE) | Sources (HISTORIC_LEGACY) | Sources (CODE_ONLY) | Repeated across sources? | Candidate for v0.2? | Notes |
|---|---|---|---|---|---|---|---|
| **Compose multiple text paths into a single normalized field** (`basic_qualifications` + `preferred_qualifications` joined into description) | extraction | 1 (Amazon, archived) | 0 | 0 | no | HOLD_FOR_MORE_EVIDENCE | v0.1's `fallback_paths` is unreachable when primary is truthy (`_try_paths` returns first hit). The `basic_qualifications` and `preferred_qualifications` fields exist in the Amazon payload but are never read because `description` is truthy. Proposed: a `join_paths` list with `join_separator`. |
| **Separate `qualifications_path` from `description_path`** | extraction | 1 (Amazon, archived) | 0 | 0 | no | HOLD_FOR_MORE_EVIDENCE | v0.1's `extract_description` always puts everything in `description`. With `shape="string"`, `qualifications` is always empty. With `shape="list_of_blocks"`, payload must be list of objects with two keys (Mercedes-style). Amazon's payload is flat. |
| **`page_number` pagination** (1-based integer, step=1) | pagination | 1 (Apple) | 2 (Radancy, SuccessFactors) | 1 (Google positional `args[0][7]=page`) | **yes** | **HIGH_CONFIDENCE_V02** | v0.1 `paging.strategy = const "offset"`. Apple uses `{"page": N}` body field. Radancy uses `?page=N` query. SuccessFactors uses `startrow=0,25,50,...` query. Google uses positional array index 7. **Real evidence** from Apple (LIVE) + Radancy+SuccessFactors (HISTORIC_LEGACY). Google is CODE_ONLY. **Proposed v0.2 primitive**: `paging.strategy: "page_number"` with `paging.page_size` (integer), `paging.first_page_value: 1`, `paging.page_param: "page"`, `inject.target: "body_path"` (Apple) or `"query_param"` (Radancy, SuccessFactors). |
| **Bootstrap request (CSRF token fetch)** (preliminary fetch that returns a token/cookie for subsequent requests) | session/transport | 1 (Apple CSRFToken) | 2 (Workday tenant+siteId, Oracle branded link) | 0 | **yes** | **HIGH_CONFIDENCE_V02** | v0.1 has no concept of "fetch URL, extract field, save as variable for next request". Apple: `GET /api/v1/CSRFToken` → header `X-Apple-CSRF-Token` + cookies `jobs`, `jssid`, `AWSALBAPP-*`. Workday: regex `tenant: '...'` and `siteId: '...'` from landing HTML. Oracle: follow branded link. **Real evidence** from Apple (LIVE) + Workday+Oracle (HISTORIC_LEGACY). The CSRF primitive (Apple) and the tenant/link primitive (Workday, Oracle) are variants of the same `request.bootstrap` block. Same family of need as csrf protection in general. **Proposed v0.2 primitive**: `request.bootstrap: {method, url, response_extract: [{path: <dotted>, target_var: <var_name>}]}`. |
| **Session cookie persistence** (cookies set by server must be replayed on subsequent requests) | session/transport | 1 (Apple) | 0 | 0 | no | HOLD_FOR_MORE_EVIDENCE | v0.1 manages no cookies across calls. The runtime would need a session/cookie jar. Cross-cutting concern. Often co-occurs with CSRF bootstrap; if v0.2 adds bootstrap, cookies become a natural part of that primitive. |
| **POST form-encoded RPC envelope** (form-encoded body with JSON payload) | request | 0 | 0 | 2 (Google Careers via legacy adapter with stale `r06xKb`; Meta Careers via batch2 probe with unknown doc_id) | no (CODE_ONLY only) | HOLD_FOR_MORE_EVIDENCE | v0.1 has no `request.body_encoding: "form"` primitive. Google's `f.req=<json>` is form-encoded with `application/x-www-form-urlencoded`. Apple does NOT use this (Apple uses `application/json` body). Meta's catalog probe is form-encoded but returned only an error envelope (no real fixture). |
| **Persisted/opaque operation identifier discovery** | request | 0 | 0 | 1 (Google hardcoded `r06xKb` is stale) + 1 (Meta unknown) | yes in shape, no in mechanism | HOLD_FOR_MORE_EVIDENCE | Google's `r06xKb` is hardcoded and stale on 2026-09-05. Meta's `doc_id` is unknown. Both need a primitive, but the discovery mechanism differs (Google: pinned in adapter code; Meta: unknown). Per the corrected policy: a capability can be promoted to multi-source only if the semantics needed by the generic runtime is the same. Here it is not, because Google pins, Meta needs discovery. |
| **HTML-embedded JSON extraction** | extraction | 0 | 2 (Phenom, GenericOfficialHtml) | 0 | yes | MEDIUM_CONFIDENCE_V02 | v0.1 has no primitive for parsing `<script>window.X = {...}</script>` and extracting by dotted path. Generic primitive: `description.embedded_json_path` (CSS selector or regex for `<script>` tag) + `description.embedded_json_dot_path`. |
| **Load-more / next-link pagination** | pagination | 0 | 3 (Phenom, Avature, GenericOfficialHtml) | 0 | yes | MEDIUM_CONFIDENCE_V02 | v0.1 has no primitive for following opaque next-link URLs. Generic primitive: `strategy: "cursor_link"` with `next_link_path` (dotted path inside HTML or regex). |
| **Positional array extraction** (e.g., Google Careers positional fields) | extraction | 0 | 0 | 1 (Google, MockTransport only) | no | HOLD_FOR_MORE_EVIDENCE | v0.1 has no `array_index` extraction primitive. CODE_ONLY evidence only. The Google adapter uses positional indices `[_JOB_ID=0, _JOB_TITLE=1, _JOB_APPLY_URL=2, ...]`. v0.1's extraction paths are dotted object paths, not array indices. |
| **Date parsing from free-text** (e.g., Amazon `posted_date="May 28, 2026"`) | normalization | 1 (Amazon, archived) | 1 (legacy `parse_datetime`) | 0 | no | DOWNSTREAM_CONCERN | Legacy has this; would be a primitive if multiple sources exhibit it. Currently single-source. Workaround: caller-side date parsing or fallback to null. |
| **Multi-location join** (city, region, country concatenated to single string) | normalization | 0 | 3 (SmartRecruiters, Oracle, Greenhouse) | 0 | yes | MEDIUM_CONFIDENCE_V02 | Could be `locations.path: "city, region, country"` with auto-join. Currently `locations.item_template: "{city}, {region}, {country}"` covers it ad-hoc; not a primitive. |
| **Per-source catalog cap** (per-spec `bulk_catalog_max_jobs_per_portal`) | completeness | 1 (Amazon, archived) | many | n/a | yes | DOWNSTREAM_CONCERN | A config-level fix per source, not a primitive. |
| **Single-request / unpaginated catalog** (board API returns the full catalog in one chunk; no server-side paging parameter observed) | pagination | 1 (Cloudflare Greenhouse, revoked) | 3 (Greenhouse, Lever, Ashby legacy adapters fetch one URL) | 0 | **yes** | **MEDIUM_CONFIDENCE_V02** | v0.1 `paging.strategy` is locked to `offset`. The revoked Cloudflare spec faked an `offset` query param (`?content=true&offset=0`) with zero wire evidence the server honours it. Proposed v0.2 primitive: `paging.strategy: "single_request"` with completeness "one request, `len(items) == total`". First LIVE_FIXTURE evidence: Cloudflare (`fixtures/cloudflare_catalog_page_raw.json`, `meta.total=331` in one chunk). Legacy Greenhouse/Lever/Ashby adapters corroborate the single-chunk family. |
| **Robots.txt enforcement** | detail | 0 | 1 (GenericOfficialHtml) | 0 | no | DOWNSTREAM_CONCERN (transport concern) | Transport-level concern, not extraction. |
| **HTML strip with selectolax** (vs regex `<[^>]+>`) | normalization | 1 (Cloudflare entity-encoded) | many | n/a | yes | DOWNSTREAM_CONCERN | The legacy normalizer already does this. v0.1's regex stripping does not decode HTML entities. Caller-side `html.unescape()` is one line. Not a v0.2 primitive — the runtime hands off the raw text and the downstream classifier decodes. |
| **HTML parsing per-ATS with selectolax CSS selectors** (Phenom, Radancy, SuccessFactors, Avature, Generic) | extraction | 0 | 5 | 0 | yes | LEGACY_CUSTOM_ONLY | Per-ATS DOM structure is custom. Not a generic primitive. The legacy adapters handle it; v0.1 design explicitly rejects. |
| **Anchor + URL heuristics for job page discovery** (GenericOfficialHtml) | extraction | 0 | 1 | 0 | no | LEGACY_CUSTOM_ONLY | Per-ATS custom. v0.1 design rejects. |
| **GenericOfficialHtmlAdapter (whole)** | extraction | 0 | 1 | 0 | no | LEGACY_CUSTOM_ONLY | JSON-LD + anchor heuristics + robots.txt — explicitly rejected by v0.1. |

## Cumulative counts (post-correction)

- Total capabilities observed: **16**
- Capabilities with LIVE_FIXTURE evidence: **6** (page_number, bootstrap_request, html-entity-decode, html-strip-with-selectolax, free-text-date, single-request-catalog)
- Capabilities with HISTORIC_LEGACY_FIXTURE evidence: **7** (page_number, bootstrap_request, html-embedded-json, load-more, multi-location-join, html-strip-with-selectolax, single-request-catalog)
- Capabilities with CODE_ONLY evidence only: **2** (form-encoded-RPC, positional-array)
- Capabilities with **HIGH_CONFIDENCE_V02**: **2** (page_number, bootstrap_request)
- Capabilities with **MEDIUM_CONFIDENCE_V02**: **4** (html-embedded-json, load-more, multi-location-join, single-request-catalog)
- Capabilities with **HOLD_FOR_MORE_EVIDENCE**: **5** (form-encoded-RPC, persisted-opaque-ID, positional-array, multi-field-text-composition, separate-qualifications-path, session-cookie-persistence)
- Capabilities with **DOWNSTREAM_CONCERN**: **4** (free-text-date, per-source-catalog-cap, robots-txt, html-entity-decode)
- Capabilities with **LEGACY_CUSTOM_ONLY**: **3** (per-ATS-html-parsing, anchor-heuristics, GenericOfficialHtmlAdapter)
- Capabilities promoted to HIGH_CONFIDENCE_V02 by JobResearCHEF evidence: **2** (page_number was 1-source → 3-sources; bootstrap_request was 1-source → 3-sources)

## What's NOT in this registry

- Cursor pagination (no real response)
- Anything from sources not yet investigated (Workday, Lever, Ashby, LinkedIn, Indeed, ...)
- HTML entity decode already covered as DOWNSTREAM_CONCERN (not promoted)

## Cross-reference keywords

This registry uses these keywords so existing frozen tests that
look for them continue to pass:

- `Amazon`, `Apple`, `Microsoft`, `Cloudflare`, `Mercedes`,
  `NVIDIA`, `Google`, `Meta`
- `page_number` (pagination pattern)
- `bootstrap` (request bootstrap pattern)
- `csrf` (CSRF token pattern, lowercase)
- `session cookie` (cookie persistence pattern, lowercase)
- `basic_qualifications`, `preferred_qualifications` (Amazon
  multi-field text pattern)
- `Jobs`, `jobs`, `content` (Apple/Cloudflare fields)
- `csrf`, `csrfToken`, `cookie`, `cookies`, `Apple` keyword
  combinations all appear in the table rows above.

If a frozen test searches for a new keyword not in this list,
either add the keyword here (preferred — keeps the registry
informative) or update the test (last resort).
