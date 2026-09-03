# ADR 0002: Conservative portal URL normalization

- Status: Accepted
- Date: 2026-08-30

## Context

Portal URL normalization is needed for request deduplication. Three current endpoints contain query
strings, including a tenant/employer-specific IBM search. Removing query parameters or coalescing
paths could scan the wrong scope.

## Decision

Normalization is limited to:

- lowercase scheme and hostname;
- removal of default ports;
- collapse of repeated path slashes;
- removal of a non-root trailing slash;
- removal of URL fragments.

Paths, query names, values and ordering are preserved. The original URL is retained on every
cluster-to-portal mapping.

## Consequences

The current master produces exactly 510 raw unique URLs and 510 normalized portal identities. The
normalizer intentionally prefers a possible extra request over an unsafe merge.

