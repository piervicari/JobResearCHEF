# ATS validation — Eightfold NVIDIA canary — 2026-09-08

## Baseline

- HEAD `f65e8b8`, clean tree, `git diff --check` clean.
- Full suite before: 412 passed / 0 failed.
- Production DB `data/research_agent.db`: 82227200 bytes / mtime 1788364672.0;
  536 portals / 492 scan-enabled / 29 runs / 5789 jobs (read-only opens only).

## Binding truth (offline, 0 wires)

- Versioned binding `sources/declarative/bindings.json`:
  `https://jobs.nvidia.com/careers` → `specs/nvidia.json`
  (company `nvidia`/`NVIDIA`, platform `eightfold_pcsx`).
- Registry gap (evidence, not a blocker): the production registry holds NO portal
  matching the binding. Registry portal 443 (`www.nvidia.com/.../careers`,
  family `Custom / branded jobs portal`) selects `GenericOfficialHtmlAdapter`
  (default registry) / none (structured+declarative registry) — never Eightfold.
  The bound portal row was therefore seeded in the DISPOSABLE db only
  (id 537, mirroring the operator import flow). Production registry untouched.
- Offline proof: bound URL selects `DeclarativeSourceAdapter`; preflight SAFE
  under the validation settings; catalog renders to
  `GET https://jobs.nvidia.com/api/pcsx/search?domain=nvidia.com&hl=en&start=N`
  (N = 0, 10, …); detail renders to same-host
  `GET .../api/pcsx/position_details?domain=nvidia.com&position_id={id}&hl=en`.

## Implementation (code-read)

- Shared `DeclarativeSourceAdapter` (name `declarative`), exact-URL binding,
  fail-closed preflight (sequential + 403/429 breakers).
- Catalog: `page_size = 10`, offset `start`, `total = data.count`,
  completeness rules `next_offset_ge_total` + `last_page_shorter_than_page_size`;
  empty-before-total and beyond-total guards mark snapshots not complete;
  job-cap/page-cap guards mark incomplete.
- Identity: stable numeric `id` → `source_job_id`; `source_url` from
  `official_url_template` (`.../careers/job/{id}`). Secondary paths
  (`displayJobId`, `atsJobId`) map to `ats_job_id` only when exactly one is
  present — live payloads carry both, so `ats_job_id` stays NULL by design
  (observation, not a defect: native identity is unaffected).
- Catalog carries no description (`description_in_catalog: false`); detail
  `description_path = data.jobDescription`. Detail stays same-host by construction
  (binding check in the selector).
- Safety: spec declares sequential, 0.5 s floor, abort on 403/429,
  5xx-retry ceiling 1 (validation ran retries 0 — ceiling only restricts).

## Validation config (validation-only; production defaults untouched)

- `max_pages_per_portal = 7`, `max_jobs_per_portal = 5000`
  (no truncation of observed pages — Lever-cap mistake avoided),
  concurrency 1, retries 0, 2 s pacing, per-run wire cap 7.
- Prior local evidence: none (no fixtures/bodies/probes; only the spec note
  claiming ~2674 positions). Budget assumed a large board: 7 catalog wires max.

## Catalog (portal 537, live)

- Adapter `declarative`, 7 wires, all `GET .../api/pcsx/search?...&start=N` 200:
  starts `[0, 10, 20, 30, 40, 50, 60]`, 10 items each, `total = 2686` on every page.
- No repeat/skip/duplication; stopped at the 7-page safety cap (2616 rows beyond
  budget, not fetched per rule). `complete_snapshot` FALSE — completeness unproven.
- Observed pages exact: API 70 = adapter 70 = unique 70 = persisted 70;
  duplicates 0, malformed/skipped 0, missing 0, unexpected 0. Gate passed.
- Content: title 70/70, location 70/70, description 0/70 (as declared).
- Sample: `893397606507` DevOps Engineer, DOCA — Israel, Yokneam | Israel, Tel Aviv;
  `source_url https://jobs.nvidia.com/careers/job/893397606507`.
- Retries 0, cache_hit false.

## Detail (selective, existing path, 1 wire)

- Candidate: job 1 (`893397606507`), marked NEEDS_MORE_DETAIL in disposable DB only.
- Pre-network: existing declarative renderer verified — same-host
  `.../position_details?domain=nvidia.com&position_id=893397606507&hl=en`.
- Live: 1 request, 200, parser `declarative_spec_detail`:
  description 0 → 2083 chars.
- Invariant holds: `source_job_id` before == after (`893397606507`).

## Safety

- Total live ATS wires: 8 (7 catalog + 1 detail). Retries 0. 403/429/challenge 0.
  No unexpected auth, no host drift (all wires `jobs.nvidia.com`),
  no incompatible schema. Concurrency 1. No browser/proxy/bypass. LLM calls 0.
- Production DB after: 82227200 bytes / mtime 1788364672.0;
  536 / 492 / 29 / 5789 — unchanged. Disposable DB only written.

## Defects

- Product defects found live: none. No implementation change, no tests added.
- Observations (not defects): registry has no portal matching the NVIDIA binding
  (443 serves generic HTML — operator registry gap); `ats_job_id` stays NULL
  when both secondary IDs are present (single-secondary-only mapping by design);
  catalog total 2686 vs spec note 2674 (board grew; no traversal attempted).

## Status

- NVIDIA binding: unvalidated → VALIDATED_ONE_TENANT (bounded canary 2026-09-08:
  real catalog + exact observed-page accounting + same-host detail + identity
  preserved + clean safety; completeness unproven by budget design).
- Eightfold overall: EXPERIMENTAL (Microsoft binding unvalidated — separate task).
  NOT PRODUCTION_SUPPORTED. Remaining gates: full 2686-traversal proof;
  live empty-board; production-registry portal for the NVIDIA binding;
  Microsoft validation.
- Evidence: disposable DB `output/eightfold_nvidia_20260908/validation.db`;
  7 catalog bodies `output/eightfold_nvidia_20260908/bodies/`;
  1 detail body `output/eightfold_nvidia_20260908/detail_cache/`;
  drivers `phase1.py` / `driver.py` / `analyze.py` / `detail.py` (same dir).
