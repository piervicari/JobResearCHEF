# 0051 — Operational Source Control Plane (V25)

**Status:** Accepted / implemented in V25
**Date:** 2026-09-03

## Decision

Adopt a structured `data/target_employers/tier_s_operational_sources_v1.csv`
as the **runtime source registry** for the Tier-S employer universe. The
`TIER_S_ATS_MAPPING.md` ledger remains the **research / audit trail** and is
no longer the runtime input. The new
`research_agent.company.tier_s_operational_sources` module is the only path
that translates the registry into `Portal` and `ClusterPortalMapping` rows.

The control plane is:

```text
structured operational source registry  (CSV)
        ↓
tier_s_operational_sources module       (deterministic, offline, additive)
        ↓
Portal + ClusterPortalMapping           (idempotent sync)
        ↓
READY_TO_PROBE / FINGERPRINT_REQUIRED / ADAPTER_NEEDED / RESOLVER_LIGHT / HOLD
```

The sync is **offline, idempotent, additive, never deletes**, and never
mutates `SourceJob`, `JobAiAnalysis`, `JobObservation` or any lifecycle
state. The existing `apply-registry-changes` workflow is **not** extended to
handle multi-source cardinality; that workflow semantically models
`old portal -> new portal` and would have to be deformed to support multiple
operational sources. The control plane is a separate path that respects the
unique (cluster, portal) constraint already enforced by the schema.

## Why

After V24 the `TIER_S_ATS_MAPPING.md` ledger was materially more advanced
than the V24 execution layer. It accumulated:

* ~225+ employers across 19 batches with strict audit-v2 evidence;
* the conclusion that the **canonical corporate identity is not the same as
  the operational source identity** (SpaceX, Discord, Coalition, Pure
  Storage/Everpure, Google/Alphabet, etc.);
* the conclusion that **most Tier-S employers fall into already-supported
  ATS families** (Greenhouse/Ashby/Workday alone cover ≥90 audit-v2
  employers), so a generic resolver-first pipeline is no longer the right
  default;
* audit-v2 evidence states (`FIRST_PARTY_VERIFIED`, `TECHNICALLY_VERIFIED`,
  `PROBABLE`, `UNVERIFIED`) that supersede the legacy `VERIFIED` label.

Without a machine-readable registry the next code change would either
re-parse the Markdown at runtime (fragile) or repeat the work by hand every
release (brittle). V25 stops treating the mapping as runtime configuration
and stops treating the registry as a static README.

## Implications

* **Research ledger vs runtime registry.** The Markdown ledger keeps its
  role as the audit trail; the CSV is the only thing the system consumes at
  runtime. Two artifacts, one source of truth (the human + the audit pass).
* **Employer vs operational source.** A `CorporateCluster` may map to
  zero, one or many operational sources via `ClusterPortalMapping`. The
  schema already supported this via `UniqueConstraint(cluster, portal)`;
  no migration is required.
* **Multi-source cardinality.** SpaceX, Discord, Coalition and any future
  multi-board employer are represented as **multiple rows in the registry
  CSV** that resolve to multiple `ClusterPortalMapping` rows. Adding a new
  source never disables or replaces an existing source.
* **Audit-v2 precedence.** The registry row's `evidence_state` field uses
  the v2 vocabulary. A `PROBABLE` row may be `READY_TO_PROBE` only if the
  `evidence_state` is `FIRST_PARTY_VERIFIED` or `TECHNICALLY_VERIFIED` *and*
  the adapter is `YES` and the `catalog_state` is not `UNTESTED`. Legacy
  `VERIFIED` text from the early batches does not pass this gate.
* **Platform verification vs catalog verification.** `evidence_state` and
  `catalog_state` are two separate columns on purpose. A source may be
  `TECHNICALLY_VERIFIED` at platform level but `PARITY_PENDING` for catalog
  completeness. `scan_enabled` may be `N` while the source is still in
  the registry; a one-shot probe is the only path to `VERIFIED`.
* **Cohort discipline.** `cohort` is restricted to `CORE_200` /
  `CORE_EXTENSION`. The CORE_200 is **frozen**. New rows after the freeze
  must use `CORE_EXTENSION` and the same audit-v2 standard.
* **Five resolution queues.** `READY_TO_PROBE`, `FINGERPRINT_REQUIRED`,
  `ADAPTER_NEEDED`, `RESOLVER_LIGHT`, `HOLD`. The next milestone consumes
  these queues and never re-asks the routing question.

## Alternatives considered

1. **Continue parsing the Markdown at runtime.** Rejected: the ledger is
   the audit trail, not configuration; Markdown is intentionally
   human-friendly and parser-fragile.
2. **Add a new `OperationalSource` table.** Rejected: `Portal` +
   `ClusterPortalMapping` already model the entity at the right
   granularity; introducing a new hierarchy would require Alembic
   migrations, multi-source fan-out in many callers and deprecation of the
   existing portal model.
3. **Extend `apply-registry-changes` to handle multi-source.** Rejected:
   the existing workflow is `old portal -> new portal` (UPDATE/RETIRE/
   SUSPEND/RESUME) and is intentionally per-cluster. Generalising it would
   deform its semantics and re-test dozens of existing cases. A separate
   path is cleaner and additive.
4. **Build a generic resolver first.** Rejected: the mapping proves the
   bulk of Tier-S already falls into supported families. The resolver is
   still wanted eventually, but it is now a *consumer* of the registry
   queues, not a gate that runs in front of every employer. The right next
   step is family-level controlled probing, not another generic tool.
5. **Continue the census.** Rejected: the CORE_200 is frozen; new
   employers must be added as `CORE_EXTENSION` and only when there is a
   concrete consumer.

## Trade-offs

* The CSV is a static artifact. It will drift from the ledger until the
  operator runs the next audit pass. The one-command script writes a
  timestamped log under `output/test_runs/` and the reports are emitted on
  every run, so drift is visible.
* The control plane does **not** invent operational URLs, ATS families or
  tokens. Rows that lack an operational URL land in `HOLD` or
  `FINGERPRINT_REQUIRED` and are explicitly listed in the queues; they
  never become `READY_TO_PROBE` automatically.
* `TIER_S_ATS_MAPPING.md` is not deleted. It remains the source of
  evidence for the next sync. If a row in the CSV disagrees with the
  ledger, the CSV wins for runtime but the discrepancy is reported
  separately as manual review.
* A registry sync never modifies `SourceJob`, `JobAiAnalysis`,
  `JobObservation` or any lifecycle state. This is a hard invariant. It
  also means the control plane is safe to run repeatedly without rolling
  back a probe.
* The control plane does not pre-detect the public Board API URL for an
  employer whose first-party page only lists human-visible jobs. Such rows
  stay in `FINGERPRINT_REQUIRED` or `RESOLVER_LIGHT`.

## Implementation implications

* `data/target_employers/tier_s_operational_sources_v1.csv`: machine-
  readable registry; 17 columns; one row per operational source.
* `src/research_agent/company/tier_s_operational_sources.py`: pure-Python
  module that loads, validates, reconciles, dry-runs and syncs.
* `tests/test_tier_s_operational_sources.py`: 13 tests covering every
  acceptance criterion + a realistic SpaceX/Discord/Coalition multi-source
  fixture.
* `src/research_agent/cli.py`: new
  `sync-tier-s-operational-sources` command.
* `scripts/prepare_tier_s_operational_sources.sh`: one-command entry
  point that always uses the persistent runtime DB at
  `~/.local/share/research-agent/research_agent.db`.
* `output/mapping/tier_s_resolution_queues.csv`,
  `output/mapping/tier_s_resolution_summary.json`,
  `output/mapping/tier_s_operational_sources_unmatched.csv`: queue + report
  artifacts.

## Status

Accepted and implemented. V25 is the milestone produced by this decision.
The CORE census is frozen. After V25 the next milestone is
**family-level controlled probing** of the `READY_TO_PROBE` queue. The
Google Careers V24 probe remains the first custom Tier-S end-to-end probe
and is not removed.
