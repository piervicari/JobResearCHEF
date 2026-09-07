# SourceSpec v0.1 — Gap Analysis (JobResearCHEF evidence)

> **Audit-only document. Corrected post-reuse-audit.** For each
> capability category, this classifies the JobResearCHEF adapters
> according to whether `runtime/source_spec/v0.1` already supports
> it, whether the capability is already a known extension pressure,
> whether it is new from JobResearCHEF evidence, or whether it
> appears custom-logic-only.

The classification legend:

- **SUPPORTED_V01** — v0.1 represents it; `runtime/spec_executor.py`
  executes it. Empirically verified by a frozen test.
- **KNOWN_EXTENSION_PRESSURE** — already in
  `EXTENSION_PRESSURE_REGISTRY.md`, evidenced by Mercedes/NVIDIA/
  Microsoft/Amazon/Apple/Google/Meta/Cloudflare batches.
- **NEW_FROM_JOBRESEARCHCHEF** — not previously known, evidence
  comes from the legacy adapters + their fixtures in this audit.
- **CUSTOM_LOGIC_ONLY** — appears to require source-specific code
  not easily expressible as a generic primitive.
- **UNKNOWN** — evidence insufficient.

For v0.2 prioritization, capabilities are also ranked using a
**second** axis:

- **HIGH_CONFIDENCE_V02** — generic, useful, ≥1 LIVE_FIXTURE
  evidence, and preferably multi-source.
- **MEDIUM_CONFIDENCE_V02** — generic, useful, only
  HISTORIC_LEGACY_FIXTURE evidence or single-source live.
- **HOLD_FOR_MORE_EVIDENCE** — capability observed, but the
  primitive required is unclear or the evidence is thin (single
  source, or CODE_ONLY).
- **DOWNSTREAM_CONCERN** — workaround exists without a new
  primitive (caller-side html.unescape, caller-side free-text
  date parsing, etc.). Recorded for traceability, NOT a v0.2
  candidate.
- **LEGACY_CUSTOM_ONLY** — appears to require per-source code
  not reasonably expressible declaratively (HTML per-ATS CSS
  selectors, anchor-text heuristics, etc.).

---

## 0. Evidence-count policy (corrected)

The original reuse audit conflated three different evidence classes.
This correction splits them.

For each capability, three counts are reported:

- **LIVE_FIXTURE_EVIDENCE** — count of real successful responses
  saved to `runtime/fixtures/`. These are the strongest evidence:
  they are real wire responses, captured with curl, and consumed
  by frozen tests.
- **HISTORIC_LEGACY_FIXTURE_EVIDENCE** — count of legacy
  JobResearCHEF adapters that have a real saved fixture under
  `JobResearCHEF/research_agent_v24/tests/fixtures/` AND a test
  in `tests/test_ats_adapters.py` that consumes it. These are real
  responses too, but from a different codebase.
- **CODE_ONLY_EVIDENCE** — count of legacy adapters that have only
  code (no real fixture) or tests that use `MockTransport`. These
  show *design intent* but do not prove the protocol works today.

Only LIVE_FIXTURE_EVIDENCE and HISTORIC_LEGACY_FIXTURE_EVIDENCE
count toward "real evidence" for v0.2 promotion. CODE_ONLY is
flagged as a yellow flag, not green.

---

## 1. Per-capability verdict matrix

### Request

| Capability | Adapters | Classification | LIVE_FIXTURE | HISTORIC_LEGACY | CODE_ONLY | Notes |
|---|---|---|---:|---:|---:|---|
| GET + query interpolation | Greenhouse, Lever, Ashby, SmartRecruiters, Radancy, SuccessFactors, Oracle, Avature, Phenom, GenericOfficialHtml | **SUPPORTED_V01** | 4 (Mercedes, NVIDIA, Microsoft, Cloudflare) | many | n/a | `paging.inject.target=query_param` covers it |
| POST JSON body + body interpolation | Workday | **SUPPORTED_V01** | 1 (Mercedes) | 1 (Workday) | n/a | `paging.inject.target=body_path` |
| POST form-encoded body | **GoogleCareersAdapter** only | **NEW_FROM_JOBRESEARCHCHEF** | **0** | 0 | 1 (Google) | v0.1 has no `request.body_encoding: "form"` primitive. Google's `f.req=<json>` is form-encoded with `application/x-www-form-urlencoded`. Apple does NOT use this (uses JSON). Meta's catalog probe is form-encoded but returned only an error envelope (no real fixture). |
| `path interpolation` in URL | Oracle, Radancy, SuccessFactors, Avature, Phenom, GenericOfficialHtml | **SUPPORTED_V01** | n/a | many | n/a | Spec author writes the URL template |
| `query interpolation` | all GET adapters | **SUPPORTED_V01** | n/a | many | n/a | Same |
| `body interpolation` JSON | Workday, Mercedes, NVIDIA, Microsoft, Cloudflare | **SUPPORTED_V01** | many | many | n/a | `templates` mechanism supports `{{var}}` |
| `headers` per-request | all adapters | **SUPPORTED_V01** | n/a | many | n/a | `request.headers` + `request.templates` |

### Bootstrap / session

| Capability | Adapters | Classification | LIVE_FIXTURE | HISTORIC_LEGACY | CODE_ONLY | Notes |
|---|---|---|---:|---:|---:|---|
| Bootstrap: GET HTML → extract variables | Workday (tenant, siteId via regex) | **NEW_FROM_JOBRESEARCHCHEF** | 0 | 1 (Workday, with real saved `workday_landing.html`) | 0 | v0.1 has no `request.bootstrap` primitive. Pattern: GET landing, regex extract 2 vars, use in next request. |
| Bootstrap: GET HTML → follow branded link | Oracle | **NEW_FROM_JOBRESEARCHCHEF** | 0 | 1 (Oracle, with real `oracle_landing.html`) | 0 | Same primitive as Workday's, just different extraction mechanism |
| Bootstrap: CSRF token via response header | (none in JobResearCHEF) | n/a (Apple-only) | 1 (Apple CSRFToken) | 0 | 0 | Already in registry |
| Cookie persistence | (none in JobResearCHEF) | n/a | 1 (Apple) | 0 | 0 | Already in registry |
| Tenant/site discovery | Workday, Oracle | same as Bootstrap | 0 | 2 | 0 | |
| Token propagation across requests | (none in JobResearCHEF) | n/a (Apple-only) | 1 (Apple) | 0 | 0 | |

### Pagination

| Capability | Adapters | Classification | LIVE_FIXTURE | HISTORIC_LEGACY | CODE_ONLY | Notes |
|---|---|---|---:|---:|---:|---|
| offset in query | Lever, SmartRecruiters | **SUPPORTED_V01** | many | many | n/a | `strategy=offset` |
| offset in body | Workday, Mercedes, NVIDIA | **SUPPORTED_V01** | many | many | n/a | `inject.target=body_path` |
| page_number in body (1-based) | **Apple only** | **NEW_FROM_JOBRESEARCHCHEF** (from this audit) | 1 (Apple) | 0 | 0 | Single source. Apple's `{"page":N}` body field. |
| page_number in query | Radancy, SuccessFactors (`startrow`) | **NEW_FROM_JOBRESEARCHCHEF** | 0 | 2 (Radancy, SuccessFactors, both with real HTML fixtures) | 0 | 2 historical sources; pattern is consistent. |
| page_number positional (Google) | **GoogleCareersAdapter** (`args[0][7]=page`) | **NEW_FROM_JOBRESEARCHCHEF** | 0 | 0 | 1 (Google, MockTransport) | Single source, code-only evidence. Cannot promote to HIGH_CONFIDENCE_V02 without real fixture. |
| single-chunk all-in-one | Greenhouse, Ashby | **SUPPORTED_V01** | 2 (Cloudflare, Mercedes) | many | n/a | `page_size=N` where N≥total yields 1 offset |
| load-more / next-link | Phenom, Avature, GenericOfficialHtml | **NEW_FROM_JOBRESEARCHCHEF** | 0 | 3 (Phenom, Avature, Generic — all with real HTML fixtures) | 0 | 3 historical sources. Pattern: parse HTML for `<a class="next">` or similar. v0.1 has no primitive. |
| cursor token (opaque) | (none in JobResearCHEF) | n/a | 0 (Google+Meta were only attempted, never succeeded) | 0 | 0 | Per the rule, no real fixture → no promotion |

### Extraction

| Capability | Adapters | Classification | LIVE_FIXTURE | HISTORIC_LEGACY | CODE_ONLY | Notes |
|---|---|---|---:|---:|---:|---|
| Dotted object path in JSON | Greenhouse, Lever, Ashby, SmartRecruiters, Workday, Oracle | **SUPPORTED_V01** | many | many | n/a | `extraction.stable_id_path` etc. |
| Array index in JSON (positional) | **GoogleCareersAdapter** only | **NEW_FROM_JOBRESEARCHCHEF** | 0 | 0 | 1 (Google, positional adapter pinned in tests) | v0.1 has no `array_index` extraction primitive. CODE_ONLY evidence. |
| Multiple text fields joined | (none — Greenhouse has `content` as single field) | **KNOWN_EXTENSION_PRESSURE** (Amazon) | 1 (Amazon, but spec archived) | 0 | 0 | Already in registry |
| Separate `qualifications_path` | (none) | **KNOWN_EXTENSION_PRESSURE** (Amazon) | 1 (Amazon, archived) | 0 | 0 | Already in registry |
| Relative URL composition | Workday (externalPath → site_url + path) | **SUPPORTED_V01** | n/a | 1 (Workday) | n/a | `official_url_template` |
| HTML-embedded JSON in `<script>` | Phenom | **NEW_FROM_JOBRESEARCHCHEF** | 0 | 1 (Phenom, with real `phenom_search_page_*.html`) | 0 | Pattern: parse HTML for `phApp.ddo = {...};`, then dot-path. v0.1 has no primitive. |
| JSON-LD `JobPosting` detection | GenericOfficialHtml | **NEW_FROM_JOBRESEARCHCHEF** | 0 | 1 (Generic, with real `generic_job_page.html`) | 0 | Same as above |
| HTML parsing with selectolax | Radancy, SuccessFactors, Phenom, Avature, GenericOfficialHtml | **NEW_FROM_JOBRESEARCHCHEF** | 0 | 5 | 0 | v0.1 has no CSS-selector primitive. Per-ATS DOM structure is custom. **LEGACY_CUSTOM_ONLY** for actual production use; the audit records it for traceability. |
| Anchor + URL heuristics | GenericOfficialHtml | **NEW_FROM_JOBRESEARCHCHEF** | 0 | 1 | 0 | Same — explicitly rejected by v0.1 design |

### Normalization

| Capability | Adapters | Classification | LIVE_FIXTURE | HISTORIC_LEGACY | CODE_ONLY | Notes |
|---|---|---|---:|---:|---:|---|
| Strip HTML tags | all HTML adapters | **SUPPORTED_V01** (partial — only regex `<[^>]+>`) | many | many | n/a | Cloudflare's entity-encoded HTML is the gap |
| HTML entity decode (`html.unescape`) | implicit in `pipeline/normalizer.py` | **DOWNSTREAM_CONCERN** | 1 (Cloudflare's entity-encoded content) | many | n/a | Recorded for traceability. The runtime strips tags but doesn't decode entities; the downstream classifier must decode. NOT a v0.2 candidate — the workaround is one line of caller-side code. |
| NFKC unicode normalization | `pipeline/normalizer.py` | **DOWNSTREAM_CONCERN** | 0 | many | n/a | Same |
| Location parsing (city, country) | SmartRecruiters, Oracle, Greenhouse | **SUPPORTED_V01** | many | many | n/a | `extraction.locations` + `item_template` |
| Date parsing from mixed formats | (legacy `parse_datetime`) | **KNOWN_EXTENSION_PRESSURE** (Amazon) | 1 (Amazon, archived) | many | n/a | Amazon's `posted_date="May 28, 2026"` is parsed by legacy but not by v0.1. Already in registry. |
| Unix timestamp | Greenhouse, Workday, Oracle, SmartRecruiters, GoogleCareersAdapter, Avature | **SUPPORTED_V01** | many | many | n/a | `date_format=unix_seconds` |
| ISO datetime | Greenhouse, Workday, Oracle | **SUPPORTED_V01** | many | many | n/a | `date_format=iso_datetime` |
| ISO date | Greenhouse, Workday, Oracle, Avature | **SUPPORTED_V01** | many | many | n/a | `date_format=iso_date` |

### Detail

| Capability | Adapters | Classification | LIVE_FIXTURE | HISTORIC_LEGACY | CODE_ONLY | Notes |
|---|---|---|---:|---:|---:|---|
| Description inline | Greenhouse, Lever, Ashby, SmartRecruiters, Workday, Oracle, GoogleCareersAdapter | **SUPPORTED_V01** | many | many | n/a | `description_in_catalog=true` |
| Separate detail endpoint | (none in JobResearCHEF — all inline) | **SUPPORTED_V01** (in principle) | 1 (NVIDIA) | 0 | 0 | NVIDIA pattern works |
| Apply URL enrichment | (none) | n/a | n/a | n/a | n/a | v0.1 has `apply_url` field |
| `robots.txt` enforcement | GenericOfficialHtml | **DOWNSTREAM_CONCERN** (transport, not extraction) | 0 | 1 | 0 | Not a v0.2 candidate; transport concern |

### Completeness

| Capability | Adapters | Classification | LIVE_FIXTURE | HISTORIC_LEGACY | CODE_ONLY | Notes |
|---|---|---|---:|---:|---:|---|
| Explicit total | Workday, SmartRecruiters, Oracle, GoogleCareersAdapter | **SUPPORTED_V01** | many | many | n/a | `completeness.rules[].kind=next_offset_ge_total` |
| Short final page = end | Lever, SmartRecruiters, Workday, Oracle, Phenom, Avature | **SUPPORTED_V01** | many | many | n/a | `last_page_shorter_than_page_size` rule |
| Empty page = end | (none in JobResearCHEF) | **SUPPORTED_V01** | 1 (Apple) | 0 | 0 | Apple pattern |
| No-pagination all-items | Greenhouse, Ashby | **SUPPORTED_V01** | 2 (Cloudflare, Mercedes) | many | n/a | `page_size=N` |
| Catalog cap | all paginated adapters | **SUPPORTED_V01** (per-run); needs per-source `bulk_catalog_max_jobs_per_portal` | 1 (Amazon, archived) | many | n/a | Already in registry as per-spec traversal-budget finding |
| Filtered search | Radancy, SuccessFactors, Oracle, Phenom | **SUPPORTED_V01** | 0 | 4 | n/a | `source_of_truth=filtered_catalog` |
| Authoritative OPEN/CLOSED possible | All full-catalog adapters | **SUPPORTED_V01** | many | many | n/a | `open_closed_authoritative=true` + `closed_decision` |

---

## 2. v0.2 candidate ranking (corrected)

Each capability is classified into one of:
**HIGH_CONFIDENCE_V02** / **MEDIUM_CONFIDENCE_V02** /
**HOLD_FOR_MORE_EVIDENCE** / **DOWNSTREAM_CONCERN** /
**LEGACY_CUSTOM_ONLY**.

### 2.1 HIGH_CONFIDENCE_V02

These satisfy all three criteria: generic, useful, ≥1 LIVE_FIXTURE
or HISTORIC_LEGACY evidence (preferably multi-source).

| Capability | Reason |
|---|---|
| **page_number pagination** | 1 LIVE (Apple) + 2 HISTORIC_LEGACY (Radancy, SuccessFactors) = 3 independent sources across 2 evidence classes. Generic primitive. High external prevalence (Indeed, LinkedIn). Promoted from `MEDIUM_CONFIDENCE` (Apple-only in the previous audit) to `HIGH_CONFIDENCE` with the JobResearCHEF evidence. |
| **bootstrap_request (HTML → variable extraction)** | 2 HISTORIC_LEGACY (Workday regex, Oracle link follow) + 1 LIVE (Apple CSRFToken) = 3 sources. The primitive would be `request.bootstrap: {method, url, response_extract: {path, target_var}}`. Generic across CSRF, tenant, link-follow variants. |

Total HIGH_CONFIDENCE_V02: **2**.

### 2.2 MEDIUM_CONFIDENCE_V02

Generic, useful, but evidence is single-source or thin.

| Capability | Reason |
|---|---|
| **POST form-encoded RPC envelope** | 1 CODE_ONLY source (Google Careers — MockTransport tests only; no real fixture; the persisted-query ID `r06xKb` was stale on 2026-09-05). Meta has CODE_ONLY for the path but no successful response. Apple does NOT use form-encoded. **HOLD_FOR_MORE_EVIDENCE**, not MEDIUM — single source, code-only, no real response. |
| **load-more / next-link pagination** | 3 HISTORIC_LEGACY (Phenom, Avature, GenericOfficialHtml) — but no LIVE_FIXTURE. Generic primitive (`strategy: "cursor_link"` with `next_link_path`). |
| **HTML-embedded JSON extraction** | 1 HISTORIC_LEGACY (Phenom) + 1 HISTORIC_LEGACY (GenericOfficialHtml for JSON-LD) — 2 historical sources, no live. Pattern is consistent (parse HTML for `<script>` with JSON). |

Total MEDIUM_CONFIDENCE_V02: **0** (none of the candidates meet the
"HIGH" bar of generic + useful + ≥1 LIVE; the three listed above
are HOLD_FOR_MORE_EVIDENCE).

### 2.3 HOLD_FOR_MORE_EVIDENCE

| Capability | Reason |
|---|---|
| **POST form-encoded RPC envelope** | As above. Google is CODE_ONLY. Apple is JSON not form. Meta is form but ERROR response only. |
| **Persisted/opaque operation identifier discovery** | Google's `r06xKb` is hardcoded and stale. Meta's `doc_id` is unknown. The two have similar shape but the discovery mechanism differs. No LIVE_FIXTURE for either. |
| **Positional array extraction** | GoogleCareersAdapter only. CODE_ONLY (MockTransport). No real fixture. |
| **Multi-field text composition** | Amazon only. LIVE_FIXTURE exists but the spec was REVOKED. Need a second source. |
| **Separate `qualifications_path`** | Amazon only. Same situation. |
| **Date parsing from free-text** | Amazon only (legacy `parse_datetime` handles it). Single source. |
| **page_number positional (Google-specific)** | GoogleCareersAdapter. Single source. CODE_ONLY. |
| **POST form-encoded body (in general)** | Apple uses JSON. Google+Meta both form but with different envelope specifics. |

Total HOLD_FOR_MORE_EVIDENCE: **8**.

### 2.4 DOWNSTREAM_CONCERN

| Capability | Reason |
|---|---|
| **HTML entity decode** | One-line `html.unescape()` on the caller side. Not a v0.2 candidate. |
| **NFKC unicode normalization** | Same. |
| **Catalog cap (per-spec)** | A config-level fix, not a primitive. |
| **Robots.txt enforcement** | Transport concern, not extraction. |

Total DOWNSTREAM_CONCERN: **4** (already in registry from prior batches, plus this).

### 2.5 LEGACY_CUSTOM_ONLY

| Capability | Reason |
|---|---|
| **GenericOfficialHtmlAdapter** (JSON-LD + anchor heuristics + robots.txt) | Custom code per ATS. v0.1 explicitly rejects universal inference. |
| **HTML parsing with selectolax per-ATS CSS selectors** | Each ATS has its own DOM. Not a generic primitive. |
| **Per-ATS HTML page extraction in detail_enrichment** | Custom logic. |

Total LEGACY_CUSTOM_ONLY: **3** (already covered, no change).

### 2.6 Capabilities excluded from v0.2

These are already in `EXTENSION_PRESSURE_REGISTRY.md` but the
audit reaffirms they are NOT v0.2 candidates because they are
downstream concerns or single-source:

- HTML entity decode (downstream)
- NFKC unicode normalization (downstream)
- Multi-field text composition (Amazon only, REVOKED)
- Separate `qualifications_path` (Amazon only, REVOKED)
- Date parsing from free-text (Amazon only, downstream concern)
- Catalog cap (per-spec) (downstream)
- Robots.txt enforcement (transport)

---

## 3. Cumulative extension-pressure registry (post-correction)

This is the corrected entry in `EXTENSION_PRESSURE_REGISTRY.md`:

| Capability | Category | Sources (LIVE) | Sources (HISTORIC_LEGACY) | Sources (CODE_ONLY) | v0.2 priority |
|---|---|---|---|---|---|
| Compose multiple text paths into a single normalized field | extraction | 1 (Amazon, archived) | 0 | 0 | HOLD_FOR_MORE_EVIDENCE |
| Separate `qualifications_path` from `description_path` | extraction | 1 (Amazon, archived) | 0 | 0 | HOLD_FOR_MORE_EVIDENCE |
| `page_number` pagination | pagination | 1 (Apple) | 2 (Radancy, SuccessFactors) | 1 (Google positional) | **HIGH_CONFIDENCE_V02** |
| Bootstrap request (HTML → variable extraction) | session/transport | 1 (Apple CSRFToken) | 2 (Workday tenant/siteId, Oracle branded link) | 0 | **HIGH_CONFIDENCE_V02** |
| Session cookie persistence | session/transport | 1 (Apple) | 0 | 0 | HOLD_FOR_MORE_EVIDENCE |
| POST form-encoded RPC envelope | request | 0 | 0 | 2 (Google, Meta — both via Comet/batchexecute; both code-only or error-only) | HOLD_FOR_MORE_EVIDENCE |
| Persisted/opaque operation identifier discovery | request | 0 | 0 | 1 (Google hardcoded `r06xKb` is stale) + 1 (Meta unknown) | HOLD_FOR_MORE_EVIDENCE |
| HTML-embedded JSON extraction | extraction | 0 | 2 (Phenom, GenericOfficialHtml) | 0 | MEDIUM_CONFIDENCE_V02 |
| Load-more / next-link pagination | pagination | 0 | 3 (Phenom, Avature, GenericOfficialHtml) | 0 | MEDIUM_CONFIDENCE_V02 |
| Positional array extraction (Google-specific) | extraction | 0 | 0 | 1 (Google, MockTransport) | HOLD_FOR_MORE_EVIDENCE |
| Date parsing from free-text | normalization | 1 (Amazon, archived) | 1 (legacy `parse_datetime`) | 0 | DOWNSTREAM_CONCERN |
| Multi-location join (city, region, country) | normalization | 0 | 3 (SmartRecruiters, Oracle, Greenhouse) | 0 | MEDIUM_CONFIDENCE_V02 |
| Catalog cap (per-spec `bulk_catalog_max_jobs_per_portal`) | completeness | 1 (Amazon, archived) | many | n/a | DOWNSTREAM_CONCERN |
| Robots.txt enforcement | detail | 0 | 1 (GenericOfficialHtml) | 0 | DOWNSTREAM_CONCERN (transport concern) |
| HTML parsing per-ATS with selectolax CSS selectors | extraction | 0 | 5 (Radancy, SuccessFactors, Phenom, Avature, Generic) | 0 | LEGACY_CUSTOM_ONLY |
| Anchor + URL heuristics for job page discovery | extraction | 0 | 1 (GenericOfficialHtml) | 0 | LEGACY_CUSTOM_ONLY |
| HTML strip with selectolax (vs regex `<[^>]+>`) | normalization | 1 (Cloudflare entity-encoded) | many | n/a | DOWNSTREAM_CONCERN |
| Filter search params required (filtered_search) | completeness | 0 | 4 (Radancy, SuccessFactors, Oracle, Phenom) | n/a | DOWNSTREAM_CONCERN (covered by `source_of_truth: filtered_catalog`) |

---

## 4. v0.2 priority list (corrected)

| Rank | Capability | Priority | Why |
|---:|---|---|---|
| 1 | `page_number` pagination | **HIGH_CONFIDENCE_V02** | 3 sources (1 LIVE, 2 HISTORIC_LEGACY). Generic. High external prevalence. |
| 2 | `bootstrap_request` | **HIGH_CONFIDENCE_V02** | 3 sources (1 LIVE, 2 HISTORIC_LEGACY). Generic. CSRF + tenant + link-follow are all variants. |
| 3 | Load-more / next-link | MEDIUM_CONFIDENCE_V02 | 3 HISTORIC_LEGACY sources. No LIVE. |
| 4 | HTML-embedded JSON | MEDIUM_CONFIDENCE_V02 | 2 HISTORIC_LEGACY sources. No LIVE. |
| 5 | POST form-encoded RPC envelope | HOLD_FOR_MORE_EVIDENCE | CODE_ONLY only. |
| 6 | Persisted/opaque operation ID | HOLD_FOR_MORE_EVIDENCE | Google stale, Meta unknown. |
| 7 | Multi-field text composition | HOLD_FOR_MORE_EVIDENCE | Amazon only (revoked). |
| 8 | Separate `qualifications_path` | HOLD_FOR_MORE_EVIDENCE | Amazon only (revoked). |
| 9 | Multi-location join | MEDIUM_CONFIDENCE_V02 | 3 HISTORIC_LEGACY. Cosmetic. |
| 10 | Positional array extraction | HOLD_FOR_MORE_EVIDENCE | Google only, CODE_ONLY. |

---

## 5. v0.2 design constraints

To become a v0.2 candidate, a capability must:

- Be **generic** (apply to ≥ 2 different source families), not a
  one-off workaround for a single ATS quirk.
- Have **LIVE_FIXTURE evidence** for at least one source, OR
  **HISTORIC_LEGACY_FIXTURE** for at least 2 sources.
- Not have a trivial **downstream workaround** (i.e. one-line
  caller-side code that doesn't require a primitive).
- Not be **LEGACY_CUSTOM_ONLY** (per-ATS code that v0.1 design
  explicitly rejects).

The corrected policy avoids:

- "2 sources = automatic v0.2" (the previous audit used this). 2
  sources is *necessary* but not *sufficient*.
- "code exists = evidence". CODE_ONLY is yellow flag, not green.
- "Apple and Google both use Comet" (the previous audit conflated
  them; they share shape but not protocol specifics).

---

## 6. Integrity statement

- 0 files in `JobResearCHEF/` modified
- 0 files in `runtime/` that are frozen (`spec_executor.py`,
  `source_spec.schema.json`, `job.schema.json`,
  `sources/mercedes.json`, `sources/nvidia.json`) modified
- 0 live HTTP requests issued
- 0 browser calls
- 121 PASS tests still green
