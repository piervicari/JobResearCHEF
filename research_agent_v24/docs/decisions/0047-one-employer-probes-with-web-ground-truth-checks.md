# 0047 — One-employer probes followed by web ground-truth checks

**Status:** Accepted workflow / Stripe probe implemented in V23  
**Date:** 2026-09-02

## Decision

After the Stripe correction probe, validate portal coverage employer-by-employer rather than scaling blindly across the 200-core universe.

Each probe should produce a single log containing:

- active operational portal/ATS;
- HTTP requests/status and discovery completeness;
- upstream/persisted job count;
- triage call count and candidate count;
- full-analysis call count;
- final SourceJob titles/statuses.

The user will provide each probe log; the research step then checks the employer's current official web careers surface independently to determine whether the scanner has materially complete coverage or a portal/backend gap.

## Why

The 10-employer core expansion proved that HTTP success is not equivalent to discovery success: multiple custom portals returned `EMPTY_INCOMPLETE`, and generic HTML produced navigation links as false jobs. Systematically comparing scanner output to current official web evidence is the fastest way to turn unknown coverage into a verified adapter/portal matrix.

## Trade-offs

This is slower than immediately scanning all 200 employers, but prevents false confidence and focuses engineering only on portals that demonstrably need a resolver/adapter correction.
