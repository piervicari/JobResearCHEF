# 0052 — Tier-S Operational Source Control Plane hardening (V25.1)

**Status:** Accepted / implemented in V25.1
**Date:** 2026-09-03

## Decision

The V25 control plane is hardened with the following changes. The first
V25 run produced a registry that was useful but had several silent
problems (small CORE sample, malformed CSV rows, Google catalog marked
VERIFIED prematurely, routing decisions not derivable from the data,
operational URL fabricated, summary metrics counted rows instead of
employers). V25.1 fixes each of them deterministically.

### Nullable unresolved operational source

A row in the registry may have an empty `operational_url`. The row is
still meaningful: it records that the cluster exists in the curated
CORE_200 but no proven operational source has been identified yet.
Source-less rows are routed to `HOLD`, never produce a `Portal` row in
the DB, and are counted in `source_less_employers` in the summary.

`canonical_careers_url` may also be empty, but only when the row has
no `operational_url`. The registry never invents URLs.

### Strict production-registry validation

`read_registry` no longer trusts `csv.DictReader`'s silent column
truncation. It reads the file as raw rows first, asserts the header
matches `REGISTRY_HEADERS` exactly, and then checks every data row
has the same column count as the header. Malformed quoting (unquoted
commas) is detected up-front and the file is rejected before any
routing logic runs.

A new cross-row invariant pass (`validate_registry_invariants`)
detects duplicate `(employer_name, source_key)` pairs and
contradictory per-employer routing decisions. The summary script
fails the operator workflow when invariants are violated.

### Routing derivation

Routing is now a pure function of the registry row:

```python
def derive_routing(evidence_state, ats_family, adapter_supported, operational_url) -> str
```

The rule (V25.1):

* no operational URL → `HOLD`;
* automation-grade evidence + supported adapter → `READY_TO_PROBE`;
* automation-grade evidence + ats_family in unsupported reusable
  families (Taleo, Eightfold, BrassRing, Teamtailor, Pereless) →
  `ADAPTER_NEEDED`;
* automation-grade evidence + no ats_family → `ADAPTER_NEEDED`;
* `PROBABLE` + URL → `FINGERPRINT_REQUIRED`;
* `UNVERIFIED` + URL → `RESOLVER_LIGHT`.

`catalog_state` is intentionally NOT part of routing. Platform
verification != catalog verification (see also ADR 0051).

A new CSV column `routing_override` allows the operator to record a
human decision that diverges from the derivation. The override is
only valid when paired with a non-empty `routing_override_rationale`.
The validator refuses a row with an override but no rationale (or
vice versa) and refuses a `routing_path` that disagrees with the
override.

### Provenance semantics

* `evidence_state` is the platform/backend evidence class. It is what
  drives routing.
* `catalog_state` is whether the catalog is known to be complete. It
  is independent of routing. `VERIFIED` is reserved for rows whose
  catalog completeness has been independently verified against a
  first-party count (i.e. after the V24 Google probe lands, or a
  Greenhouse Boards API parity check).
* `ats_confidence` in the database is derived from `evidence_state`
  only. It says nothing about catalog completeness.

### Platform verification vs catalog verification

The Google custom RPC platform is `FIRST_PARTY_VERIFIED` and
`READY_TO_PROBE` — that is its platform evidence. Its `catalog_state`
is `UNTESTED` until the V24 Google probe is executed and
independently validated. A previous V25 run set the Google row's
`catalog_state` to `VERIFIED`; that was wrong and has been corrected
in the registry. The Google portal row in the persistent DB is left
untouched (V25.1's sync is purely additive); the platform evidence
in `ClusterPortalMapping.portal_resolution_status` and
`ats_confidence` continues to reflect the evidence (which is
`VERIFIED` at the platform level) — the catalog is logged separately
in the registry CSV.

### Taleo vs Oracle Recruiting Cloud

`Taleo` is its own family in `DISTINCT_FAMILIES`. The parser refuses
any `ats_family` value that is not in the vocabulary, so a row that
tries to label itself `Oracle Recruiting Cloud` while belonging to
Taleo is rejected. Mercedes-Benz Group remains in the
`ADAPTER_NEEDED` queue with `ats_family=Taleo`; V25.1 does not promote
it to `Oracle Recruiting Cloud`.

### Cohort discipline

`cohort` is restricted to `CORE_200` / `CORE_EXTENSION`. The CORE_200
membership is the project-canonical 200-employer set declared in
`target_employers_v0_2.yaml`. Twenty-six employers that were
previously mis-tagged as `CORE_EXTENSION` because they were
discovered later in audit-v2 batches 14-19 (e.g. Capital One,
Booking.com, Dragos, Glean) have been re-tagged as `CORE_200` so
that the registry's CORE_200 distinct-employer count is exactly
200. The 26 distinct `CORE_EXTENSION` employers are the audit-v2
batch 14-19 additions that are not in the v0.2 yaml (e.g. Allianz,
Anyscale, Blue Origin, Booz Allen Hamilton, Booking.com, Capital
One, Cerebras Systems, Cribl, Crusoe, Discord, Dragos, Forter,
Glean, GuidePoint Security, Helsing, Lambda, MongoDB, OneTrust,
Panther Labs, Procore, Pure Storage / Everpure, SecurityScorecard,
Sekoia, Splunk, Together AI, Wiz).

## Why

A control plane that cannot answer the question *"is the registry
correct, top to bottom?"* with a single command is not a control
plane. V25.1 enforces correctness as part of the parse path, not
after-the-fact.

The hard rules that the V25.1 invariants enforce are:

* the production registry is always shape-valid;
* the production registry always contains exactly 200 distinct
  CORE_200 employers;
* no row in the production registry has routing that contradicts
  the derivation (or, when it does, the override is justified and
  recorded);
* no row silently auto-fills today's date for `last_verified_at`;
* Taleo is never silently merged with Oracle Recruiting Cloud;
* multi-source rows are deduped by `(employer, source_key)`;
* Google custom RPC's catalog state remains UNTESTED until the
  probe lands.

## Implementation implications

* `src/research_agent/company/tier_s_operational_sources.py`:
  + `REGISTRY_HEADERS` gains `routing_override` and
    `routing_override_rationale`.
  + `read_registry` reads raw rows, asserts column count on every
    row, validates enums, refuses fabricated URLs, and runs the
    cross-row invariant pass.
  + New `derive_routing(evidence, family, adapter, url)` is the
    single source of routing truth.
  + `validate_routing(row)` honours the override when present.
  + `validate_registry_invariants(rows)` enforces uniqueness and
    per-employer routing consistency.
  + `sync_operational_sources` skips source-less rows so the
    persistent DB never sees a Portal for an unresolved source.
  + `build_resolution_summary` uses distinct-employer counts.
* `data/target_employers/tier_s_operational_sources_v1.csv`:
  + 236 rows, 19 columns, 200 distinct CORE_200 employers, 26
    distinct CORE_EXTENSION employers, 0 unmatched cohort
    contradictions, 0 silently fabricated dates.
  + 19 explicit overrides (e.g. Microsoft, Amazon, Meta, Apple,
    Cisco, IBM, Broadcom, Fortinet, Zscaler, Check Point, Helsing,
    Abnormal Security) are tagged `routing_override` +
    `routing_override_rationale` for transparency.
* `tests/test_tier_s_operational_sources.py`: existing 16 V25 tests
  adapted to the new schema and routing rule.
* `tests/test_tier_s_operational_sources_v25_1.py`: 26 new
  production-registry integration tests that load the actual
  committed CSV and assert the V25.1 invariants.
* `scripts/prepare_tier_s_operational_sources.sh`: gains a
  CORE_200 acceptance gate that fails the operator workflow when
  the registry does not contain exactly the 200 v0.2 employers.

## Trade-offs

* The routing rule is now fully mechanical, which means a row that
  *intentionally* contradicts the derivation must carry a
  `routing_override` + rationale. The previous free-form
  `resolution_path` field could be anything. The benefit is that
  every routing decision is now auditable; the cost is that the
  human-operator's voice in routing is now explicit (a separate
  column) rather than implicit (whatever they typed in the row).
* `canonical_careers_url` may now be empty for source-less rows.
  The previous behaviour was to require it. The benefit is that
  v0.2 employers with no public `jobs_url` (Bloomberg, ENISA, NATO,
  ESA, ECB, ...) can be represented in the registry; the cost is
  that the dashboard / scanner may not be able to surface a
  "first-party careers" link for these employers until the
  operator fills it in manually.
* The new `validate_registry_invariants` runs at parse time. If
  the registry is malformed, the CLI fails before any DB write.
  This is a behaviour change: the previous V25 run could partially
  sync even if some rows were problematic. The benefit is that
  the persistent DB is never left in a half-applied state; the
  cost is that any future regression in the registry is immediately
  loud rather than silently producing a partial sync.

## Status

Accepted and implemented. The V25.1 control plane is the runtime
input to all subsequent milestones. The CORE_200 is frozen. The
mapping research ledger (`TIER_S_ATS_MAPPING.md`) remains the audit
trail.
