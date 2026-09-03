# Testing strategy

## Goals

Tests must prove parser contracts, deterministic classification, lifecycle safety and bounded network
behavior without depending on live third-party services. Live probes provide operational evidence but
are not a replacement for repeatable offline tests.

## Offline verification

Run before every handoff:

```bash
uv run ruff check .
uv run pytest -q
uv run research-agent benchmark-taxonomy
```

The test suite must not require credentials or Internet access. HTTP behavior is exercised with
in-process mock transports and sanitized fixtures.

The `offline-verification` workflow in `.github/workflows/ci.yml` repeats these gates on Python 3.12,
reconstructs registry state from the immutable v1.5 plus every versioned correction/wave artifact,
imports reviewed aliases and performs a backup/recovery drill. It does not call third-party portals.

For a release audit from a disposable database, run:

```bash
bash scripts/final_audit.sh
```

The script deletes only its own `mktemp` directory on exit. It leaves the working database and
versioned evidence untouched.

## Test layers

- Unit tests: normalization and cyber, seniority and geography rules.
- Adapter contract tests: routing, URL derivation, parsing, pagination, schema errors and snapshot
  completeness.
- Pipeline tests: concurrency, per-host interval, retry/backoff, cache, failure isolation and metrics.
- Persistence tests: master import, deduplication, immutable observations and lifecycle advancement.
- Acceptance tests: frozen master counts and source-asset coherence.
- Benchmark tests: labeled examples and precision/recall thresholds independent from hand-written
  unit assertions.

The versioned benchmark is `data/benchmarks/taxonomy_v1.csv`. Its labels express product policy and
must not be changed merely to make a regression pass. A disputed label should be reviewed as a policy
decision, with the reason recorded in the dataset or an ADR.

## Fixtures

Fixtures derived from public services must contain the minimum response fields needed to express the
contract. Remove personal contact details, tracking tokens, cookies and irrelevant descriptions.
Record the source family and capture date in the test or fixture metadata; do not claim that a fixture
proves current live availability.

## Live validation

Live validation is manual and bounded. It requires the pre-scan gate in
[`OPERATIONS.md`](OPERATIONS.md), explicit portal IDs, a named purpose and a report containing request,
retry, status, job-count and unexpected-empty metrics. A successful small cohort proves only that
cohort at that time.

## Release evidence

A release or milestone report must include exact commands, timestamps, test counts, selected Portal
IDs or a reproducible selection rule, configuration snapshot and known residual risks. Historical
reports are retained rather than rewritten to imply broader coverage.

## V15 targeted-detail baseline validation — 2026-09-02

The complete repository suite was executed in the sandbox with a minimal BeautifulSoup-backed compatibility stub for the unavailable native `selectolax` package. Result: **190 passed**. The stub supports the CSS/text methods exercised by the test suite but is not a substitute for running the same suite with real `selectolax` on the user's macOS environment. Python compile validation also passed.

New coverage includes:

- generic `Find Jobs` navigation exclusion;
- detail JobPosting JSON-LD parsing and main-text fallback;
- effective AI input preferring detail fields and changing its input hash after enrichment;
- existing payload/dedup/lifecycle/router/pilot behavior.
