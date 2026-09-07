# JobResearCHEF

Local-first research agent that monitors curated employers through their
official career sites / ATS sources and uses an LLM to interpret job
semantics (cybersecurity).

Three areas — do not confuse them:

1. `research_agent_v24/` — the production application
   (code, tests, data, canonical documentation).
   Start here: `research_agent_v24/README.md`.
2. `external_reuse_audit/` — offline/external ATS and company-registry
   evidence plus frozen external reference checkouts. Research input only,
   never a runtime dependency. See `external_reuse_audit/README.md`.
3. `runtime/` — historical declarative-prototype evidence. NOT production.
   See `runtime/README.md` before touching anything inside.

Current state for the next agent:
`research_agent_v24/docs/CODEX_HANDOVER_CURRENT.md`.
