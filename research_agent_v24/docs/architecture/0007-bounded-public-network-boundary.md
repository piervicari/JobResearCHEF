# ADR 0007: Bounded public network boundary and pre-lifecycle cohort gate

- Status: Accepted
- Date: 2026-08-31

## Context

Registry URLs are curated operator inputs today, but redirects, DNS answers and remote bodies are
untrusted. The initial fetcher accepted any HTTP(S) host, delegated redirects to the client, loaded
unbounded bodies and had no overall run deadline. A network or parser anomaly could therefore reach a
private address, consume excessive resources, keep a run open too long or advance lifecycle state
before cohort-level anomalies were reviewed.

## Decision

- Resolve hostnames and reject non-public literal or resolved addresses before every request.
- Follow redirects explicitly, reapplying destination and per-host rate checks at every hop.
- Reject credentials in URLs and HTTPS-to-HTTP downgrade redirects by default.
- Bound redirect count, response bytes, per-request time, retries, `Retry-After` and total run time.
- Record redirects as network attempts without misclassifying them as retries.
- Create an integrity-checked online SQLite backup before a CLI live scan by default.
- Assess failure rate, retry rate, `429` responses and complete empty snapshots after fetch but before
  vacancy lifecycle processing. A failed gate preserves scan evidence and skips processing.

## Consequences

The scanner fails closed on unresolved or mixed public/private DNS and on redirects that cross the
trust boundary. Some legitimate sites with unusual DNS or insecure redirects may require source
resolution rather than a permissive exception. Operators may explicitly disable a pre-scan backup,
but the CLI emits a warning. DNS validation does not cryptographically pin a connection to the
validated address, so only curated registry targets should be accepted until a transport-level pinning
design is justified.
