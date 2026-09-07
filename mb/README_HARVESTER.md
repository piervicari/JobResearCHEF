# Mercedes-Benz Career Harvester

A deterministic, idempotent, conservative harvester for Mercedes-Benz career vacancies that are likely related to cybersecurity, AI safety, data protection, vehicle cyber, etc. It does NOT classify jobs semantically — it only collects them so a downstream LLM can decide.

## Endpoint used

The only endpoint hit by this harvester is:

```
POST https://jobs.api.mercedes-benz.com/search
```

Payload (validated during discovery):

```json
{
  "LanguageCode": "EN",
  "SearchParameters": {
    "FirstItem": 1,
    "CountItem": 50,
    "Sort": [{"Criterion": "PublicationStartDate", "Direction": "DESC"}]
  },
  "SearchCriteria": [
    {"CriterionName": "PositionFormattedDescription.Content", "CriterionValue": ["cybersecurity"]}
  ]
}
```

Two important lessons from discovery, encoded in the harvester:

1. The free-text search criterion name is `PositionFormattedDescription.Content` (not `Keyword`).
2. Omitting `MatchedObjectDescriptor` from the request returns ALL fields, including `PositionLocation` and the full `PositionFormattedDescription`. Setting it to any whitelist causes the server to drop those fields. The harvester never sets `MatchedObjectDescriptor`.

The harvester also enforces a hard **single-host allowlist** — anything other than `jobs.api.mercedes-benz.com` raises `SafetyAbort`.

## Paging strategy

* `CountItem = 50` per request.
* The API returns `SearchResultCountAll` (total in catalog) and `SearchResultItems` for the current window.
* The harvester pages through each keyword until either the next page is empty, the cumulative offset passes the total, or a defensive 5-page (250 items) cap is reached.
* Across all 22 keywords the cumulative unique PositionID count observed during discovery was ~120, so the cap is purely a safety belt.

## Detail strategy

The "detail" of a job IS its `MatchedObjectDescriptor` from the same search endpoint — there is no separate detail endpoint. **As of the post-discovery revision the harvester makes ZERO additional detail requests.** The catalog response already contains the full `PositionFormattedDescription` (Tasks + Qualifications), so a second pass would just re-download what we already have.

* **Catalog pass** (every run, every keyword): we call the search endpoint and read the full `MatchedObjectDescriptor` from the response. We compute three hashes per row: `metadata_hash`, `description_hash`, `semantic_hash`.
* **UNCHANGED PIDs** (metadata_hash AND description_hash match the stored ones): zero requests, just an `UPDATE last_seen_run_at`.
* **NEW PIDs**: zero additional requests. Always flag `needs_semantic_analysis = 1`.
* **POSSIBLY_CHANGED PIDs** (metadata_hash OR description_hash differs): zero additional requests. Re-flag `needs_semantic_analysis` ONLY if `semantic_hash` differs from the stored one — metadata-only tweaks (e.g. apply-URI rotation) update the row but do NOT trigger a new LLM call.

This change dropped the bootstrap from 78 requests (39 catalog + 39 detail) to ~39 requests — and a normal-run with no changes is exactly 39 catalog requests with zero detail traffic.

## The three hashes

| Hash | Inputs | Used for | When it changes |
|---|---|---|---|
| `metadata_hash` | `PositionTitle`, `DepartmentName`, `ParentOrganizationName`, dates, `PositionLocation`, `CareerLevel`, `JobCategory`, `TargetGroup`, `PositionOfferingType`, `PositionSchedule`, `PositionURI`, `ApplyURI` | Change detection (cheap, fast comparison). | Any metadata field is updated. |
| `description_hash` | `Tasks` + `Qualifications` text only (HTML-stripped, whitespace-normalised) | Change detection: catches description edits that don't move the title/department. | The job description or qualifications text is edited. |
| `semantic_hash` | `PositionTitle` + `DepartmentName` + Tasks + Qualifications | Decision: does this PID need a new LLM classification? | The title, department or description text changes. Company / location / dates / URLs do NOT affect this hash. |

Hash inputs are HTML-stripped before hashing, so re-rendering the same description with new tags or new indentation does NOT produce a spurious description_hash mismatch.

## Pagination and catalog completeness

* The harvester pages through each keyword by incrementing `FirstItem` by the page size until either the cumulative offset passes `SearchResultCountAll` or the response is empty.
* **There is NO per-keyword page cap.** The only thing that stops pagination is the global safety circuit breaker (`max_requests_per_run`). Removing the per-keyword cap was deliberate: a hidden cap that ends a sweep without reaching `SearchResultCountAll` would silently leave the catalog incomplete.
* `catalog_complete` is `True` iff every keyword's pagination ended by reaching `SearchResultCountAll`. Any safety event (breaker trip, 403, 429, persistent 5xx after retries, network errors past `max_consecutive_errors`) flips it to `False`.
* When `catalog_complete == False`, the `closed_pids` set is left empty and `closed_calculation_skipped` is set to `True`. No destructive update is applied based on absence of evidence.

## Retry semantics

* `max_retries_on_5xx = 1` means EXACTLY 1 original attempt + 1 retry = 2 wire attempts in total. This applies identically to HTTP 5xx and to network errors (`URLError`, `TimeoutError`, `OSError`).
* The condition is `attempts <= self.max_retries_5xx`. With `max_retries_5xx = 1`, `attempts = 1` (the original attempt) is allowed to retry; `attempts = 2` aborts. Concretely: original + 1 retry = 2 wire attempts.
* 403 and 429 are NEVER retried, regardless of `max_retries_on_5xx`. They bump their respective counters and abort the run immediately.

## Pacing

In production we use:

| Setting | Value | Why |
|---|---|---|
| `min_seconds_between_requests` | 1.2 | Discovery ran at ~0.5s without blocks; we add ~0.7s of margin. |
| `jitter_seconds_max` | 0.4 | Small uniform jitter to spread the load. NOT meant to evade any anti-bot. |
| `long_pause_every_n_requests` | 25 | After every 25 requests, sleep 6s. |
| `long_pause_seconds` | 6.0 | |
| `max_requests_per_run` | 600 | Hard ceiling. Bootstrap of 22 keywords * ~2 pages ≈ 44 catalog requests; subsequent runs ~44 catalog + 0 detail. |

All pacing is `time.sleep(...)` based, single-threaded. No async, no threading, no multiprocessing, no `asyncio.gather`.

## Behavior on 403 / 429

* The harvester does **not** retry on 403 or 429.
* It does **not** rotate User-Agent.
* It does **not** switch network identity.
* It records the status, increments `http_403_count` / `http_429_count`, sets `aborted_for_safety = true` in `run_summary.json`, saves whatever catalog state was already collected, and exits cleanly.

For 5xx or network errors:

* Up to `max_retries_on_5xx` (default 1) retry with `retry_after_5xx_seconds` (default 30s).
* If still failing, abort cleanly without corrupting state.

If `max_consecutive_errors` is exceeded, also abort cleanly.

A single global circuit breaker: `max_requests_per_run` (default 600). When hit, the harvester aborts immediately.

## Schema SQLite

Table `jobs` (created automatically):

| Column | Type | Notes |
|---|---|---|
| `source_job_id` | TEXT PRIMARY KEY | `PositionID`, e.g. `mer00046gt`. Stable across catalog refreshes. |
| `internal_id` | TEXT | Backend `ID`, e.g. `231512`. May rotate; we don't key off it. |
| `title` | TEXT | `PositionTitle` |
| `company` | TEXT | `ParentOrganizationName` |
| `department` | TEXT | `DepartmentName` |
| `locations_json` | TEXT | JSON of `PositionLocation[]` |
| `job_url` | TEXT | `PositionURI` |
| `apply_url` | TEXT | first entry of `ApplyURI[]` (Taleo) |
| `publication_start` | TEXT | ISO date |
| `publication_end` | TEXT | ISO date |
| `position_start` | TEXT | ISO date |
| `description` | TEXT | Tasks HTML-stripped + whitespace-normalised. Stored ONLY after a successful fetch; not always present on UNCHANGED rows. |
| `qualifications` | TEXT | Qualifications HTML-stripped + whitespace-normalised. Same lifecycle as `description`. |
| `metadata_hash` | TEXT NOT NULL | sha256 over METADATA_FIELDS (everything below except description text). |
| `description_hash` | TEXT | sha256 over `Tasks` + `Qualifications` text only (HTML stripped). Independent of metadata. |
| `semantic_hash` | TEXT | sha256 over the fields whose change should trigger a new LLM classification: `PositionTitle` + `DepartmentName` + Tasks + Qualifications. Excludes company, location, dates, URLs, career level. |
| `first_seen_at` | TEXT | UTC ISO |
| `last_seen_at` | TEXT | UTC ISO |
| `last_seen_run_at` | TEXT | UTC ISO (updated every run) |
| `is_open` | INTEGER | 1 / 0 |
| `needs_semantic_analysis` | INTEGER | 1 = needs downstream LLM |
| `last_seen_keyword` | TEXT | keyword that surfaced this PID last |

`description` and `qualifications` are stored HTML-stripped — the same normalisation the hashes use — so the LLM downstream receives clean text.

Indices: `ix_jobs_is_open`, `ix_jobs_needs_semantic`.

The harvester also runs idempotent migrations to add the three hash columns if the DB was created by an older harvester version.

## Bootstrap

```
python3 mercedes_harvester.py --bootstrap
```

* Runs the catalog pass for every configured keyword. Each catalog response already includes the full description and qualifications, so NO detail pass is needed.
* Writes all rows to SQLite.
* `needs_semantic_analysis` is set to **0** for bootstrap rows — they are NOT emitted to `new_or_changed_jobs.json` because the assumption is that bootstrap is used to seed the local state, and the *next* normal run will only flag genuinely new jobs.
* `output/run_summary.json` records `catalog_jobs_seen`, `http_requests_total`, `catalog_complete`, `closed_calculation_skipped`, etc.

## Normal run

```
python3 mercedes_harvester.py
```

For each PositionID currently in the catalog:

| Catalog state | DB state | Decision |
|---|---|---|
| Seen | Not in DB | NEW → upsert, flag `needs_semantic_analysis = 1` |
| Seen | Same `content_hash` | UNCHANGED → only update `last_seen_run_at` |
| Seen | Different `content_hash` | POSSIBLY_CHANGED → compare old vs new `full_hash`; if description text actually changed, flag for semantic analysis, otherwise treat as unchanged |
| Not seen | In DB and was open (and `catalog_complete == true`) | CLOSED → set `is_open = 0` |
| Not seen | In DB and was open (and `catalog_complete == false`) | **NOT** closed. The DB stays untouched for this PID. |

`output/new_or_changed_jobs.json` is rewritten each run, containing ONLY rows that need downstream classification.

## Catalog completeness and CLOSED detection

The harvester tracks whether the catalog sweep finished:

* `catalog_complete == true`: every configured keyword was searched without safety abort. CLOSED is computed as `known_pids - seen_pids` and applied.
* `catalog_complete == false`: some keyword search was aborted (403/429/circuit-breaker/5xx/network). The `closed_pids` set is left **empty** — no destructive update is performed based on absence of evidence. The summary records `catalog_complete: false`, `catalog_incomplete_reason: "<reason>"`, and `closed_calculation_skipped: true`.

The DB schema, `last_seen_run_at` updates, and writes for the PIDs we DID see are flushed even on partial abort (try/finally around the run body), so the database is always consistent with whatever partial catalog we managed to gather.

## How new / changed / closed are detected

* **NEW** = catalog contains a PositionID that is not in `jobs.source_job_id`.
* **UNCHANGED** = `metadata_hash` AND `description_hash` of the catalog row equal the previously stored ones.
* **POSSIBLY_CHANGED** = `metadata_hash` OR `description_hash` differs from the stored one. We then compare `semantic_hash` (computed from the SAME catalog response's title + department + description text):
  * If `semantic_hash` is unchanged, the delta is purely metadata (e.g. apply-URI rotation) → the DB row is updated but `needs_semantic_analysis` stays **0**. No LLM call is owed.
  * If `semantic_hash` differs → the title, department or description text actually changed → flag `needs_semantic_analysis = 1`.
* **CLOSED** = `is_open = 1` row that did not appear in this catalog sweep AND `catalog_complete == true`. If the catalog was incomplete, the same row stays `is_open = 1` until the next successful sweep proves it's gone.

`PositionID` is the primary identity. It was stable across the entire discovery sweep and across all keywords, including across the German / English / Hungarian language variants.

## Outputs

```
mb/
├── mercedes_jobs.db             # SQLite state
├── output/
│   ├── run_summary.json         # stats for this run
│   └── new_or_changed_jobs.json # ONLY jobs needing semantic classification
```

`run_summary.json` fields:

* `started_at`, `finished_at`, `mode`
* `catalog_complete`, `catalog_incomplete_reason`, `closed_calculation_skipped`
* `catalog_jobs_seen`
* `new_jobs`, `changed_jobs`, `unchanged_jobs`, `seeded_jobs`, `closed_jobs`
* `http_requests_total` (real wire attempts, used by the circuit breaker)
* `catalog_requests`, `detail_requests` (logical metrics; `detail_requests` is always 0 now)
* `http_403_count`, `http_429_count`, `http_5xx_count`, `http_network_error_count`
* `errors` (list)
* `aborted_for_safety`, `abort_reason`

### `seeded_jobs`

A bootstrap-specific count. The harvester's bootstrap mode never classifies rows as `new_jobs` / `changed_jobs` / `unchanged_jobs` — by design, those numbers would be misleading because there is no prior DB state to compare against. Instead, the summary reports `seeded_jobs` = number of rows inserted. The very next normal run will then produce meaningful `new_jobs`, `changed_jobs`, and `unchanged_jobs` numbers by comparing against the freshly seeded baseline.

## Assumptions made

1. `PositionID` is the stable identity of a Mercedes-Benz career posting. Across the discovery sweep (22 keywords, 2 sweeps, 36 requests) the same vacancy always appeared under the same `PositionID`.
2. The endpoint and the request shape don't change silently. If Mercedes changes the API, the harvester will log a non-JSON parse error and abort cleanly.
3. The three-hash split (`metadata_hash` for cheap change detection, `description_hash` for description-only edits, `semantic_hash` for the LLM reclassification decision) accurately separates "the description changed" from "the job moved to a different office". This depends on the Mercedes API not introducing new fields that affect cyber classification without also being captured by `semantic_hash` — we currently hash `PositionTitle + DepartmentName + Tasks + Qualifications`.
4. The user wants ONLY positions that touch cybersecurity / AI safety / data protection / vehicle cyber. We monitor a curated list of keywords that produced cyber-relevant results during discovery. This is a candidate-generation step, not a classifier.
5. The first run is the bootstrap. All subsequent runs are idempotent: catalog unchanged ⇒ zero new_jobs, zero changed_jobs, zero detail_requests, minimum request count (one per configured keyword).

## Residual risks

* **API surface changes** — if Mercedes adds a captcha, a mandatory cookie, or changes the search payload shape, the harvester will start failing. The safety circuit breaker handles that gracefully (no retries, no IP rotation, clean exit).
* **Keyword drift** — Mercedes may publish cyber jobs whose description doesn't contain any of our 22 keywords. Adding more keywords is a config-only change but doesn't change the architecture.
  * A single `--probe-full-catalog` request (see "Probing the full catalog" below) confirmed the entire Mercedes catalog has 2798 active vacancies; a full sweep would cost 56 requests vs 44 for the current keyword sweep. The keyword sweep is currently the better trade-off, but if recall matters more than traffic, switch the harvester to a full-catalog pass by removing the `SearchCriteria` from `catalog_request` in `mercedes_harvester.py`.
* **Race with publication window** — a job that opens and closes between two sweeps is invisible to us. We rely on a daily cadence (or whatever the user runs the harvester at) to mitigate this.
* **Single-process state** — if two harvester runs execute simultaneously they will compete for the SQLite file. WAL mode allows concurrent reads but not concurrent writes from competing processes. Run sequentially.
* **Bootstrap noise** — bootstrap writes every seen row. If the catalog is very large this could exceed `max_requests_per_run`. Raise the cap if needed.

## Probing the full catalog

```bash
python3 mercedes_harvester.py --probe-full-catalog
```

Sends a single POST with empty `SearchCriteria` and reads `SearchResultCountAll` to estimate the cost of a full-catalog sweep. Does NOT walk through the catalog. Live result observed during this revision:

```json
{
  "total_full_catalog": 2798,
  "estimated_full_catalog_requests": 56,
  "current_keyword_sweep_requests": 44,
  "more_efficient": "keyword_sweep",
  "better_recall": "full_catalog"
}
```

Conclusion: a full-catalog pass would cost ~27% more requests but guarantee 100% recall. The keyword sweep is the right default for a conservative harvester.

## Tests

The repository contains `test_harvester_local.py` — a fully offline test suite. It uses a mock HTTP state machine and never makes real network calls. The suite covers EXACTLY the following ten scenarios; it is not "exhaustive" — anything not listed below is NOT covered:

1. `test_idempotent_run` — bootstrap + normal run with an identical catalog yields `new_jobs=0, changed_jobs=0, unchanged_jobs=N` and zero detail traffic on the second run.
2. `test_partial_catalog_429_leaves_db_consistent` — HTTP 429 mid-sweep does NOT mark previously-known rows as CLOSED and emits `closed_calculation_skipped=true`.
3. `test_partial_catalog_does_not_close_after_real_prior_state` — seed the DB with rows that are absent from the partial catalog; they stay `is_open=1`.
4. `test_breaker_counts_real_attempts_including_retries` — a 5xx + retry increments `http_requests_total` exactly twice.
5. `test_breaker_trips_on_real_attempts` — the global circuit breaker trips before the next wire attempt when `max_requests_per_run` is reached.
6. `test_run_catches_safety_abort_keeps_db_consistent` — `SafetyAbort` is caught by the run loop, the DB stays queryable, `run_summary.json` is still written.
7. `test_description_only_change_triggers_semantic_analysis` — modify ONLY Tasks/Qualifications → row flagged for semantic analysis, `metadata_hash` unchanged, `semantic_hash` changed.
8. `test_metadata_only_change_does_not_trigger_semantic_analysis` — change only `apply_uri` → DB row updated, `needs_semantic_analysis` stays 0, `new_or_changed_jobs.json` is empty.
9. `test_pagination_cap_cannot_claim_complete` — when the breaker trips mid-sweep, `catalog_complete` is `false`, `closed_calculation_skipped` is `true`, no job is closed. The per-keyword cap is gone: the only thing that can stop pagination is the breaker.
10. `test_exactly_one_retry_means_two_wire_attempts` — with `max_retries_on_5xx=1`, a 500 followed by 500 aborts; `http_requests_total=2` and the third scripted OK response is left untouched.

```bash
python3 test_harvester_local.py
```

## Quick start

```bash
cd mb
python3 mercedes_harvester.py --bootstrap
python3 mercedes_harvester.py
python3 mercedes_harvester.py     # third run should be a no-op
```
