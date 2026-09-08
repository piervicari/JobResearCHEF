# ATS validation — Eightfold Microsoft canary — 2026-09-08

## Baseline

- HEAD `2c79384`, clean tree apart from staged Part-A hygiene (see below),
  `git diff --check` clean.
- Full suite before: 412 passed / 0 failed.
- Production DB `data/research_agent.db`: 82227200 bytes / mtime 1788364672.0;
  536 portals / 492 scan-enabled / 29 runs / 5789 jobs (read-only opens only).

## Binding truth (offline, 0 wires)

- Versioned binding `sources/declarative/bindings.json`:
  `https://careers.microsoft.com` → `specs/microsoft.json`
  (company `microsoft`/`Microsoft`, platform `eightfold_pcsx`).
- Registry gap (same pattern as NVIDIA): production registry holds NO portal
  matching the binding. Registry portal 187
  (`jobs.careers.microsoft.com/global/en/search`, family `Custom Microsoft
  Careers`, HEALTHY) selects `GenericOfficialHtmlAdapter` (default) / none
  (structured+declarative) — never Eightfold. The bound portal row was seeded
  in the DISPOSABLE db only (id 537). Production registry untouched.
- Offline proof: bound URL selects `DeclarativeSourceAdapter`; preflight SAFE;
  catalog renders to
  `GET https://microsoft.eightfold.ai/api/pcsx/search?domain=microsoft.com&hl=en&start=N`;
  detail renders to same-API-host
  `GET .../api/pcsx/position_details?domain=microsoft.com&position_id={id}&hl=en`
  (cross-host vs the portal URL, spec-sanctioned — allowed by the selector's
  explicit detail-host rule).

## Spec (code-read, differences from NVIDIA)

- Identical envelope/paths/field names; page_size 10, offset `start`,
  `total = data.count`, stable numeric `id`, no catalog description.
- Differences only: host (`microsoft.eightfold.ai`), domain (`microsoft.com`),
  `official_url_template`
  (`https://apply.careers.microsoft.com/careers/job/{id}`). No NVIDIA
  assumptions were forced; Microsoft behavior documented as observed.
- Spec note claimed total 2252; live total fluctuated 2179–2182 (board churn).

## Validation config (validation-only; production defaults untouched)

- `max_pages_per_portal = 7`, `max_jobs_per_portal = 5000`, concurrency 1,
  retries 0, 2 s pacing, per-run wire cap 7.

## Catalog (portal 537, live)

- Adapter `declarative`, 7 wires, all `GET .../api/pcsx/search?...&start=N` 200:
  starts `[0, 10, 20, 30, 40, 50, 60]`, 10 items each,
  totals `[2181, 2182, 2181, 2181, 2179, 2179, 2182]` (live churn; warning fired).
- Stopped at the 7-page cap. `complete_snapshot` FALSE — full completeness unproven.
- Observed pages exact as sets: API 70 = adapter 70 = unique 66 = persisted 66.
  4 native IDs repeated across consecutive pages (1 on starts 0&10; 3 on 50&60)
  — offset-shift from the churning board; persistence correctly keeps 1 row per
  native ID. Duplicates-from-pagination 4 (deduped), malformed/skipped 0,
  missing 0, unexpected 0. Gate passed.
- Content: title 66/66, location 66/66, description 0/66 (as declared).
- Sample: `1970393556984938` Account Executive, Government —
  Canada, Alberta, Edmonton;
  `source_url https://apply.careers.microsoft.com/careers/job/1970393556984938`.
- Retries 0, cache_hit false.

## Detail (selective, existing path, 1 wire)

- Candidate: job 1 (`1970393556984938`), NEEDS_MORE_DETAIL in disposable DB only.
- Pre-network: existing declarative renderer verified — sanctioned detail host
  `microsoft.eightfold.ai`, exact `position_details` URL.
- Live: 1 request, 200, parser `declarative_spec_detail`:
  description 0 → 6686 chars.
- Invariant holds: `source_job_id` before == after (`1970393556984938`).

## Safety

- Total live ATS wires: 8 (7 catalog + 1 detail). Retries 0. 403/429/challenge 0.
  No unexpected auth, no host drift (catalog/detail all `microsoft.eightfold.ai`),
  no incompatible schema. Concurrency 1. No browser/proxy/bypass. LLM calls 0.
- Production DB after: 82227200 bytes / mtime 1788364672.0;
  536 / 492 / 29 / 5789 — unchanged. Disposable DB only written.

## Defects

- Product defects found live: none. No implementation change, no tests added.
- Observations (not defects): registry gap (187 vs binding); live total churn
  2179–2182 with cross-page ID repeats handled exactly once each;
  `ats_job_id` NULL (both secondary IDs present — single-secondary-only mapping
  by design, same as NVIDIA).

## Status

- Microsoft binding: UNVALIDATED → VALIDATED_ONE_TENANT (bounded canary
  2026-09-08: real catalog + exact observed-page set accounting under live churn
  + sanctioned-host detail + identity preserved + clean safety; completeness
  unproven by budget design).
- Eightfold overall: EXPERIMENTAL → MULTI_TENANT_VALIDATED (NVIDIA +
  Microsoft: two distinct real bindings through the production ingestion
  architecture, stable native identities, exact observed accounting, detail
  success on both, clean safety, no unresolved defect). This is
  protocol/binding validity, NOT full-catalog completeness proof.
  NOT PRODUCTION_SUPPORTED. Remaining gates: full traversal of a large
  catalog; live empty board; production-registry routing for both bindings.
- Evidence: disposable DB `output/eightfold_microsoft_20260908/validation.db`;
  7 catalog bodies `output/eightfold_microsoft_20260908/bodies/`;
  1 detail body `output/eightfold_microsoft_20260908/detail_cache/`;
  drivers `driver.py` / `analyze.py` / `detail.py` (same dir, git-ignored).
