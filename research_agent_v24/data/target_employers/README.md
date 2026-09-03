# Target employers

This directory contains the human-curated operational employer universe.

- `target_employers_v0_1.yaml`: proposed manual S/A/B list and current runtime coverage.
- `target_employers_v0_1_coverage.csv`: flat coverage view.
- `target_employers_v0_1_report.md`: actionable coverage and queue report.
- `tier_s_portal_resolution_lite_v0_1.csv`: manually researched Tier-S portal candidates that should be applied before arbitrary portal-resolution waves.

The list is explicit product configuration, not an automatically ranked universe. A portal candidate does not mean the runtime DB has already been mutated; Codex should validate and apply it through a versioned registry change.

## Tier-S resolution research

- `tier_s_portal_resolution_lite_v0_1.csv`: machine-readable candidates/actions.
- `tier_s_portal_resolution_lite_v0_1.md`: human rationale, evidence notes, and activation safeguards.

These files are research inputs. They do not mutate the active portal registry by themselves.


## Active pilot set

`target_employers_v0_2.yaml` is the accepted cyber-pilot core set. All 200 entries are core/Tier-S membership for the pilot. Scan cadence is intentionally not derived from this tier; see decision 0011 and `docs/ROADMAP_V2.md`.
