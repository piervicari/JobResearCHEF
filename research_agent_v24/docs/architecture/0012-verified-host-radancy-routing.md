# ADR 0012: Verified-host routing for shared Radancy markup

Date: 2026-08-31

## Decision

Route the Radancy/TalentBrew adapter only when both the host and search-result path have been reviewed
against the observed public server-rendered contract. Do not route from an ATS-family label or from
host similarity alone.

The adapter may claim a complete snapshot only when parsed unique job IDs equal the public total.
Page, job, host and run budgets still apply; reaching any cap makes the snapshot incomplete.

## Consequences

Shared markup creates leverage without turning pattern matching into unsupported vendor detection.
Landing pages and larger boards remain safe: they either stay on fallback or stop incomplete.
