# Contributing

The project is a local-first, manually operated research tool. Changes must preserve its conservative
network behavior, auditable data model and deterministic inclusion rules.

## Development setup

Requirements are Python 3.12+ and `uv`.

```bash
uv sync --dev
uv run pytest
uv run ruff check .
```

Install optional dependencies only for the capability being tested:

```bash
uv sync --extra dashboard
```

Browser automation is not a project dependency or scanner capability; see ADR 0008.

## Change workflow

1. Read [`docs/STATUS.md`](docs/STATUS.md), the relevant ADRs and
   [`docs/OPERATIONS.md`](docs/OPERATIONS.md).
2. Keep source-adapter changes isolated. Add a captured, sanitized fixture and contract test before
   treating a new response shape as supported.
3. Keep tests offline by default. Live evidence gathering must be a separate, bounded, manually
   invoked operation.
4. Run the narrow tests while iterating, then the complete verification suite.
5. Update configuration examples, operational documentation, status and reports in the same change
   when their claims are affected.

## Engineering invariants

- A scan requires explicit portal IDs, an explicit limit or the deliberate `--all` opt-in.
- Portal Registry targets are deduplicated before network access.
- A failed or incomplete snapshot cannot close a vacancy.
- Inclusion decisions remain deterministic and auditable. An LLM must not write directly into the
  inclusion path.
- LinkedIn remains a manual, user-supplied import. Do not automate login or scrape authenticated
  pages.
- Do not bypass `robots.txt`, CAPTCHA, access controls or rate limits.
- Treat remote response bodies, redirects and imported CSV content as untrusted input.
- Never overwrite the authoritative master dataset in place. Derived waves are versioned artifacts.

## Adapter acceptance checklist

An adapter is not complete until all of the following are true:

- routing is narrow enough to avoid claiming unrelated portals;
- the public endpoint and URL derivation are backed by observed evidence;
- success, pagination, malformed schema, non-2xx behavior and safety caps are tested;
- completeness semantics are explicit;
- fixture provenance and sanitization are documented;
- a bounded live probe succeeds without login or protection bypass;
- `adapter-coverage` changes are reviewed for unexpected routing expansion.

## Definition of done

A change is done when code, tests and documentation agree; the full offline suite passes; any live
validation is separately identified; generated artifacts can be traced to their inputs; and no
known safety regression is left undocumented. See [`docs/TESTING.md`](docs/TESTING.md) for the
verification commands.
