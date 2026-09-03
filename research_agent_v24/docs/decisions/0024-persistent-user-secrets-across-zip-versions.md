# 0024 — Persistent user secrets across ZIP versions

Status: ACCEPTED
Date: 2026-09-02

## Decision

Do not copy API keys into versioned project ZIPs. Load a stable per-user secrets file from:

`~/.config/research-agent/.env`

before the project-local `.env`.

The distributed ZIP may contain a harmless `.env` file with comments but no credentials.
`research-agent bootstrap-secrets` can migrate the newest useful `.env` from an older sibling
`research_agent*` extraction into the persistent path without printing secret values.

## Why

The user downloads every project revision into a new directory. Re-copying `.env` manually is
unnecessary friction, while embedding live credentials into every ZIP would multiply secret
copies and increase accidental disclosure risk.

## Precedence

1. explicit shell/CI environment variables;
2. `~/.config/research-agent/.env`;
3. project-local `.env` as a development convenience.

## Security

The bootstrap applies mode `0600` on POSIX systems on a best-effort basis and never logs key
values. The persistent file must remain outside project archives and source control.
