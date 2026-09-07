# Cloudflare — `NEEDS_EXTENSION` (corrected after offline re-evaluation)

## Status

This document supersedes the PASS_V01 verdict recorded in
`BATCH3_META_CLOUDFLARE_REPORT.md`. Offline re-evaluation with the existing
fixtures (zero new HTTP) found that the candidate spec misrepresents the
wire protocol: it declares an `offset` pagination that was never observed
server-side.

The old `candidates/cloudflare.json` has been moved to
`candidates/_archive/cloudflare.json.PASS_V01_then_revoked`. No active
`candidates/cloudflare.json` exists. No fake offset pagination is live.

| Dimension | Value |
|---|---|
| `contract_fit` | **NEEDS_EXTENSION** |
| `missing_capability` | `single_request / unpaginated catalog` |
| `semantic_complete` | **true** (title, department, description blob all extract; see caveat below) |
| `normalized_text_clean` | **false** — Greenhouse returns the `content` field HTML-entity-encoded (`&lt;`, `&gt;`, `&quot;`); v0.1 `strip_html` removes `<tag>` markup but does not decode entities. Downstream must call `html.unescape()` before classification |
| `traversal_complete_under_safety_policy` | **false** under v0.1 (see finding) |
| `authoritative_for_closed` | **not demonstrated via v0.1** |
| `browser_required` | false |

## What was re-verified offline (zero HTTP, only existing fixtures)

### Finding: fake offset pagination

The real Greenhouse Job Board API response (`fixtures/cloudflare_catalog_page_raw.json`,
5.5 MB, `meta.total = 331`) carries the COMPLETE catalog in a single chunk.
The probe that captured it was:

`GET https://boards-api.greenhouse.io/v1/boards/cloudflare/jobs?content=true`

with NO offset/page parameter. No second page was ever fetched; no
offset parameter was ever shown to change the response. There is zero
evidence that the endpoint honours an `offset` (or any paging) query
parameter server-side.

The revoked spec nevertheless declared:

- `paging.strategy = "offset"`, `page_size = 331`, `first_page_value = 0`,
  `page_param = "offset"`, `inject.target = "query_param"`
- completeness rules `next_offset_ge_total` + `last_page_shorter_than_page_size`

Consequences:

1. `render_catalog_request(spec, 0)` emits `?content=true&offset=0` — a
   parameter the server was never observed to accept. If the server
   ignores unknown params, the sweep accidentally works; if it rejects
   them, the sweep breaks. Either way the spec asserts protocol
   behaviour with no wire evidence: a fake pagination declaration.
2. `pagination_iterator(spec, total=331)` yields exactly one offset (`0`),
   and with the revoked rule set (`items_path_empty_after_total` absent)
   no empty-after-total probe is required — so `evaluate_completeness`
   can report complete on a single chunk. That is the correct *shape*
   for this source, but v0.1 reaches it only by coincidence of tuning
   (`page_size == total`), not by declaring "this catalog is a single
   request". Any future catalog growth past 331 silently breaks the
   invariant with no signal.
3. The honest declaration would be a `single_request` (unpaginated)
   paging strategy: exactly one catalog request, completeness iff that
   one request succeeded and `len(items) == total`. v0.1 has no such
   strategy — `paging.strategy` is locked to `offset`.

Hence `contract_fit = NEEDS_EXTENSION` with missing capability
`single_request / unpaginated catalog` (category: pagination).

### Semantic note (unchanged from Batch 3)

`semantic_complete = true`: `title`, `departments.0.name`, and the full
HTML `content` blob (about + responsibilities + qualifications +
benefits as one document) all extract. The downstream classifier
receives the full text in `description`; qualifications text is
*contained* in it, just not split into a separate normalized field.
`normalized_text_clean = false` because of the entity-encoding quirk
(`html.unescape()` required downstream — Greenhouse wire-format quirk,
not a v0.1 bug).

## Minimal generic primitive (NOT implemented)

```json
"paging": {
  "strategy": "single_request",
  "page_size": null,
  "first_page_value": null
}
```

with completeness rule "single chunk: `len(items) == total` on the one
and only request". Generically useful (any single-chunk board API:
Greenhouse, Lever, Ashby). Deferred to v0.2 with this source as first
LIVE_FIXTURE evidence.

## Fixtures preserved

- `fixtures/cloudflare_catalog_page_raw.json` (5.5 MB raw capture)
- `fixtures/cloudflare_catalog_page.json` (cleaned, 838 KB)
- `fixtures/cloudflare_detail.json` (14 KB)
- `candidates/_archive/cloudflare.json.PASS_V01_then_revoked` (revoked spec)
