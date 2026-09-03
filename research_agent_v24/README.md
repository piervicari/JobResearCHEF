# RESEARCH AGENT - PIER

> **V2 pilot note (2026-09-02):** the current product direction is documented in `docs/ROADMAP_V2.md`, `docs/V2_QUICKSTART.md` and `docs/decisions/`. The historical deterministic MVP described later in this README is retained for provenance but is **not** the V2 product path. V2 stores discovered source jobs before semantic processing, keeps all cybersecurity seniorities, and delegates job semantics to the routed `JobAnalyzer`. Use `scan-discover` / `analyze-pending`, not legacy `scan-official` / `reclassify-current`, for V2 testing.

MVP local-first per la ricerca manualmente avviata di vacancy cybersecurity junior,
graduate e internship. Il sistema separa rigorosamente:

```text
company universe -> portal registry -> job observations
```

Il file autorevole storico e' `data/company_universe/master_company_universe_v1_5_portal_resolution_wave5.csv`;
il corrente snapshot sincronizzato e'
`data/company_universe/master_company_universe_v1_10_portal_resolution_wave6.csv`. Le Wave 1-5 non
vengono ricostruite. Correzioni e Wave 6 sono batch versionati; gli asset originali nella root sono
conservati come consegna immutata.

## Avvio locale

Requisiti: Python 3.12+ e `uv`.

```bash
uv sync --dev
uv run research-agent init-db
uv run research-agent import-master
uv run research-agent validate-master --report docs/reports/milestone_1_validation.md
uv run pytest
```

Controllare il routing degli adapter senza fare rete:

```bash
uv run research-agent adapter-coverage
```

Una scansione richiede sempre un limite esplicito o una lista di Portal ID. Per esempio:

```bash
uv run research-agent scan-official --portal-id 160 --portal-id 177
```

`--all` e' disponibile solo come opt-in esplicito. Non e' stato usato durante lo sviluppo MVP.

Dashboard locale:

```bash
uv sync --extra dashboard
uv run --extra dashboard streamlit run src/research_agent/dashboard/app.py
```

LinkedIn e' integrato nell'MVP tramite import manuale controllato, senza scraping o automazione di
login. Copiare e compilare `data/import_templates/linkedin_jobs.csv`, quindi:

```bash
uv run research-agent ingest-linkedin-csv path/to/linkedin_jobs.csv
```

Dopo una modifica alla tassonomia, riclassificare gli snapshot correnti senza rete:

```bash
uv run research-agent reclassify-current
```

Misurare precisione e recall dei filtri sul benchmark etichettato, sempre senza rete:

```bash
uv run research-agent benchmark-taxonomy
```

Il database SQLite predefinito e' `data/research_agent.db`. Puo' essere cambiato con
`RESEARCH_AGENT_DATABASE_URL`.

## Stato verificato

- Milestone 1: tutti i sei acceptance criteria esatti sono PASS.
- Routing: 123 portali strutturati e 369 fallback HTML incompleti attualmente scansionabili. I contratti
  SuccessFactors, Workday, Phenom, Oracle Recruiting Cloud e Avature hanno fixture e canary live.
- Rollout: le coorti corrette da 50 e 100 hanno superato il gate; il run 26 ha avuto 8% di failure,
  zero retry e zero `429`.
- Tassonomia: benchmark versionato di 212 casi, decisione finale 100% e gate 95% PASS.
- Dashboard: review, lifecycle confidence, portal health, adapter coverage e cluster prioritari.
- Wave 6: 100 cluster prioritizzati, 15 risolti da fonti ufficiali e 85 differiti senza mapping
  forzato; il master v1.10 conserva 12.503 record.
- Qualita': 169 test, master validation, benchmark, dashboard smoke, audit da database vuoto,
  backup/recovery e Ruff PASS. La verifica offline e' anche codificata in CI.

Il dettaglio corrente e' in `docs/STATUS.md` e
`docs/reports/adapter_rollout_2026-08-31.md`. Il routing al fallback HTML non equivale a copertura
strutturata verificata.

## Vincoli MVP

- nessun people research o CV fit;
- niente ruoli SWE generici o senior;
- Italia inclusa e Middle East escluso;
- HTTP/API only nel runtime corrente; l'automazione browser e' esclusa da ADR 0008;
- nessun bypass di login, CAPTCHA o rate limit;
- dedup prima per Corporate Cluster ID, poi per Jobs Search URL normalizzato;
- provenance e auditability sono parte del modello dati.

Le decisioni architetturali, lo stato delle milestone e l'analisi critica sono in `docs/`.
L'indice della documentazione e' in `docs/README.md`; prima di una scansione live leggere il
runbook `docs/OPERATIONS.md` e la policy `SECURITY.md`.

## Current one-command operator flow

For the current V2/P0 path, prefer:

```bash
./scripts/run_core_trial.sh
```

The script syncs development + dashboard dependencies, reuses persistent secrets, initializes/migrates the persistent runtime DB at `~/.local/share/research-agent/research_agent.db`, ensures the Streamlit dashboard is running at `http://127.0.0.1:8501`, and then launches the bounded core-employer expansion. A healthy managed dashboard is not started twice.


## V23 — Stripe structured-source probe

The first core expansion showed that an HTTP-200 corporate careers page can still be `EMPTY_INCOMPLETE`. Stripe is now resolved to its Greenhouse operational source while the Stripe careers page remains canonical. To test the correction and the large-batch free-LLM triage path:

```bash
./scripts/run_stripe_greenhouse_probe.sh
```

The script reuses the persistent runtime DB/dashboard, applies the versioned Stripe registry correction idempotently, scans the Greenhouse catalog with the existing low-request envelope, triages up to 2,000 Stripe jobs in batches of 100, runs the full JobAnalyzer only on candidates, and writes `output/test_runs/stripe_greenhouse_probe_*.log`.


## V24 — Google structured-RPC probe + narrower CYBER boundary

Stripe proved the technical pipeline but exposed semantic overreach into payment fraud, AML/financial crime and generic enterprise risk/compliance. V24 narrows both LLM contracts without introducing keyword/regex membership rules (`cyber-triage-v2`, `cyber-job-v4`).

Google is the next Tier-S employer. The current careers frontend exposes a structured anonymous `batchexecute` search RPC; `GoogleCareersAdapter` consumes that platform contract instead of crawling result/detail HTML. The Google-specific full-catalog request budget is isolated to the probe script; ordinary scanner defaults are unchanged.

Run:

```bash
./scripts/run_google_careers_probe.sh
```

The script uses `~/.local/share/research-agent/research_agent.db`, ensures the managed dashboard, scans the Google catalog sequentially, runs 100-job high-recall triage batches plus candidate-only rich analysis, and writes `output/test_runs/google_careers_probe_*.log`. Upload that log before declaring Google PASS/FIX; the result must be compared against current web-visible Google security vacancies.
