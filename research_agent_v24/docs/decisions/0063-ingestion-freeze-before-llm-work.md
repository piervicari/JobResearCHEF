# Decision 0063: ATS ingestion reliability must be validated and frozen before resuming LLM classification work

- Status: ACCEPTED
- Date: 2026-09-08

## Decision

Freeze all LLM-side work (routing, prompts, triage/analyzer changes, model
maintenance) until the ingestion layer earns trust per ATS. Trust is recorded
in `docs/ATS_VALIDATION_MATRIX.md` with levels EXPERIMENTAL /
VALIDATED_ONE_TENANT / MULTI_TENANT_VALIDATED / PRODUCTION_SUPPORTED /
NEEDS_EXTENSION / BLOCKED — evidence-gated, never test-count-gated.

## Rationale

- Canary #2 proved the pipeline can persist, triage, and hydrate correctly —
  then analysis failed on provider-side 404/503s. Chasing provider churn
  while ingestion coverage is unproven multiplies unknowns.
- The Oracle adapter-name defect (detail keyed `oracle`, real name
  `oracle_recruiting_cloud`) survived unit tests and died on first live
  contact: only live tenants expose integration truth. The Honeywell
  PENDING_AI row stays deferred evidence, not a debt to fix now.

## Tradeoff

- Accepts: slower visible AI progress; some canaries end PARTIAL_* on empty
  boards or provider outages.
- Rejects: scaling sources or tuning models atop unvalidated ingestion.

## Implementation consequence

- Validation runs one ATS at a time, ≤3 catalog wires + ≤1 detail wire per
  tenant, disposable DBs, zero AI in the loop (manual ≤1 detail pick).
- Per-ATS reports under `docs/reports/ats_validation_<provider>_*.md`.
- ExternalSourceCandidate lazy validation stays deferred until adapters that
  would serve resolved candidates are multi-tenant validated.

## Freeze criteria (INGESTION_V1, not frozen yet)

- Matrix established with Tier-1 decided (supported or explicitly limited).
- Cross-tenant live evidence per general-purpose ATS (target 3 tenants).
- Source resolution reliable; bounded safety validated; cohort ingestion OK.
- No major open dedup/lifecycle issue.

## AI deferred status

- No triage/analyze/routing/prompt/model work until INGESTION_V1.
- OpenRouter free-slug 404s + Gemini 503 observed 2026-09-08 are recorded
  telemetry for later routing maintenance, not current work.
