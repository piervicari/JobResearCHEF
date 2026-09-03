# 0042 — Persistent runtime database across code versions

**Status:** Accepted / implemented in V22  
**Date:** 2026-09-02

## Decision

Move the operator/pilot runtime SQLite database out of versioned ZIP directories and use a stable user-local path by default:

`~/.local/share/research-agent/research_agent.db`

The first V22 run seeds this database from the newest prior `research_agent*/data/pilot/research_agent_pilot.db` if available, migrates it additively, and then keeps using the same runtime DB across later code versions.

## Why

The V15–V20 test sequence exposed repeated operational friction from copying a SQLite database between numbered extracted project folders. Schema migrations and state continuity became more failure-prone than the actual scanner/LLM pipeline. A code release ZIP is not the right home for mutable runtime state.

This mirrors decision 0024 for secrets: code snapshots are disposable/versioned; user runtime state is persistent.

## Implications

- future ZIPs do not need to copy the pilot DB from the previous ZIP on every run;
- dashboard and scanner can point at the same stable database even when code is updated;
- additive `create_schema()` still runs before use;
- existing sibling pilot DB import remains available for historical/recovery workflows but is no longer the normal operator path;
- database backups must target the persistent runtime path.

## Trade-offs

A user-local DB is less self-contained than a project-folder DB, but state continuity and dashboard correctness are more important for an operational agent. The path can be overridden with `RESEARCH_AGENT_RUNTIME_DB_PATH`.
