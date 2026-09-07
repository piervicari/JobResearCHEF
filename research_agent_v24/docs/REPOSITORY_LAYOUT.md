# Repository layout (canonical)

Repo root is `JobResearCHEF/`. Three top-level areas with different
ownership — check this file before adding anything.

```text
JobResearCHEF/
├── README.md                      # 3-area orientation (this file's parent)
├── .gitignore                     # hygiene: .DS_Store, __pycache__, *.py[cod]
├── research_agent_v24/            # CANONICAL PRODUCT
│   ├── README.md                  # product scope, setup, operator flow
│   ├── src/research_agent/        # CANONICAL PRODUCTION RUNTIME
│   │   ├── sources/ats/           # ATS adapters (incl. teamtailor, workable)
│   │   ├── sources/declarative/   # DeclarativeSourceAdapter + specs
│   │   ├── pipeline/              # HttpFetcher, scanner, lifecycle
│   │   ├── company/               # registry, ExternalSourceCandidate importer
│   │   ├── db/                    # models (SourceJob, ExternalSourceCandidate…)
│   │   └── ai/                    # JobAnalyzer routing
│   ├── tests/                     # offline tests + fixtures/
│   ├── config/                    # ScannerSettings / operator config
│   ├── data/                      # company universes (canonical: v1_12),
│   │                              # target employers, runtime DB-adjacent state
│   ├── scripts/                   # operator scripts
│   ├── docs/                      # CANONICAL DOCUMENTATION
│   │   ├── CODEX_HANDOVER_CURRENT.md  # current state (read first)
│   │   ├── REPOSITORY_LAYOUT.md       # this file
│   │   ├── ROADMAP_V2.md              # forward plan (CURRENT section on top)
│   │   ├── OPERATIONS.md / TESTING.md # operator + test policy
│   │   ├── decisions/             # decision log 0001–0060 (target behavior)
│   │   ├── architecture/          # implemented-system ADRs
│   │   ├── reports/               # immutable run/dataset evidence
│   │   └── archive/               # retired docs (historical, keep links working)
│   └── output/                    # generated run output (not evidence)
├── external_reuse_audit/          # EXTERNAL EVIDENCE / RESEARCH, NON-RUNTIME
│   ├── README.md                  # purpose + network + provenance rules
│   ├── vendor/                    # frozen checkouts, never dependencies
│   ├── wave1_probes/              # saved controlled-probe bodies
│   └── ATS_REUSE_WAVE1_1.md       # current protocol decisions
└── runtime/                       # PROTOTYPE / HISTORICAL, NON-RUNTIME
    ├── README.md                  # non-canonical banner + rules
    ├── fixtures/ sources/ candidates/  # frozen prototype inputs (read-only)
    └── *_REPORT.md reuse_audit/   # historical prototype evidence
```

(`mb/` and `NVIDIA/` at root are single-employer probe workspaces from
earlier milestones — historical, not product, not evidence inputs.)

## Ownership rules

- Production code lives ONLY in `research_agent_v24/src/`. Nothing else
  in the repo executes in production — not `runtime/`, not
  `external_reuse_audit/`, not `mb/`/`NVIDIA/`.
- Tests for production code live ONLY in `research_agent_v24/tests/`.
- Current documentation lives ONLY in `research_agent_v24/docs/`.
  Do not duplicate current state into root-level or sibling files.
- `external_reuse_audit/` holds external evidence and audit scripts.
  Reuse outcomes are re-implemented as house adapters under `src/`; the
  audit directory itself never becomes a dependency.
- `runtime/` holds frozen prototype artifacts. Production work MUST NOT
  be implemented there; adopted capabilities canonicalize under `src/`.
- `docs/reports/` entries are immutable snapshots: never rewrite them to
  match later behavior — add a new dated report instead.
- Do NOT move data files (company-universe CSVs, candidate CSVs, raw probe
  bodies, fixtures) as part of documentation work.
