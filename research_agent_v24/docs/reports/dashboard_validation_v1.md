# Operator dashboard validation

Date: 2026-08-31

## Delivered views

- An actionable review queue exposes component ambiguity reasons, company-resolution method,
  sources, apply link and lifecycle confidence.
- Canonical jobs and all active source jobs expose `complete`/`incomplete` lifecycle confidence.
- Portal health includes warnings, latest attempt/error, snapshot completeness, access state,
  cooldown, circuit-breaker reason and scan-enabled state.
- Operational failures are classified as stale route, robots denial, access denial, schema drift or
  transient failure; never-scanned and warning states remain distinct.
- Coverage includes structured versus incomplete fallback adapters and a deterministic high-value
  unresolved-cluster shortlist.
- Run history remains separate from current portal state.

On the current database, the dashboard explains 40 review jobs, 5,228 active sources, 509 registry
portals and 477 scannable portals. Source lifecycle evidence is 2,073 complete and 3,155 incomplete;
20 current review jobs have at least one complete source and 20 are incomplete-only.

## Verification

- Query and classification tests pass inside the 158-test offline suite.
- Streamlit started headlessly on localhost and rendered HTTP/UI state successfully.
- Browser inspection verified all five tabs and the key review, lifecycle, issue, adapter, unresolved
  cluster and run-history views.
- A visual inspection of Portal health showed metrics, filters and registry rows with no console
  errors.
