# Research Agent — execution roadmap v2

Updated: 2026-09-02

This roadmap supersedes the **product direction** of the original `docs/ROADMAP.md`. The original file remains historical evidence of the deterministic-filtering MVP that Codex completed. V2 optimizes for using the system as soon as possible.

## Product invariant

```text
Human-curated core employers
        ↓
Official career portals / ATS
        ↓
Discover job postings
        ↓
LLM semantic classification + analysis
        ↓
Persist ALL cybersecurity jobs, regardless of seniority
        ↓
Lifecycle/history + dashboard
        ↓
Later: alerts / program intelligence / expanded domains
```

**Code owns mechanics. LLM owns job semantics.**

No deterministic keyword/seniority/geography logic may decide whether a discovered job is cybersecurity, what seniority it has, or what the role means.

---

# P0 — Make the cyber scanner usable

## P0.0 Low-impact live canary before rollout

Before any core-employer live rollout, execute the staged canary policy in decision `0013` / `docs/LIVE_CANARY_TEST_PLAN.md`. Use a disposable DB, explicit lower-criticality portal IDs, concurrency 1, one page per portal, zero retries and strict request budgets. Do not use `--all`.

P0 ends when the user can run the system manually and inspect a useful database/dashboard of current cybersecurity jobs across the core employers.

## P0.1 Core employer set

- Use `data/target_employers/target_employers_v0_2.yaml`.
- 200 employers are CORE targets for the cyber pilot.
- Do not continue generic Wave 7/8 expansion.
- Resolve/fix curated portal gaps in parallel; do not block first use on all 200 becoming perfect.

Current baseline:

- 200 core employers.
- 157 already have a scannable portal in the current registry.
- 43 require resolution/runtime work.
- More than 100 core-employer rows currently point to scannable portals with no successful scan recorded yet; unique-portal counts are lower because portals may be shared.

## P0.2 Replace semantic deterministic filtering

Remove `VacancyFilter` as a gate for canonical persistence.

The scanner may still use deterministic code for:

- HTTP/API access;
- ATS parsing;
- pagination;
- normalization of mechanically structured values;
- company/portal identity;
- deduplication;
- schema validation;
- lifecycle;
- retries/rate limits;
- persistence.

It must **not** use deterministic title/description/seniority/geography rules to determine cyber relevance or role meaning.

## P0.3 Add a durable discovery/classification queue

Do not make successful scans depend synchronously on an LLM API being available.

Recommended minimal state machine:

```text
DISCOVERED
   ↓
PENDING_AI
   ↓
┌───────────────┬────────────────────┬───────────────┐
│ CYBER         │ NEEDS_MORE_DETAIL  │ NON_CYBER     │
│ persist       │ enrich/fetch       │ prune/archive │
└───────────────┴────────────────────┴───────────────┘
```

A temporary durable queue is allowed to contain non-cyber discoveries until classification completes. The **product cyber job dataset** retains all cyber jobs, every seniority.

This queue prevents:

- losing discoveries during LLM outages;
- re-scanning a portal simply because AI processing failed;
- coupling network reliability to model reliability.

## P0.4 JobAnalyzer: batch LLM classification + minimal enrichment

Implement one simple orchestrator called `JobAnalyzer`.

It sends batches through an explicit task route and requests structured output. The current P0 `job_analysis` lane is Gemini 3.6 Flash high -> OpenRouter MiniMax-M3:free, with free-only fallback routing, five-minute per-attempt timeouts, live heartbeat progress, and schema micro-repair. Gemini 3.7 Flash is temporarily disabled after repeated live timeout/503 evidence. The 2026-09-02 five-job micro-canary was accepted as sufficient to proceed; model-vs-model benchmarking is not a P0 blocker.

Minimum output per candidate job:

```json
{
  "job_id": "...",
  "is_cybersecurity": true,
  "needs_more_detail": false,
  "role_family": "Security Engineering",
  "specializations": ["Application Security"],
  "seniority": "senior",
  "years_experience_min": 5,
  "years_experience_max": null,
  "skills_required": ["Python", "threat modeling"],
  "skills_preferred": [],
  "degree_requirement": null,
  "certifications": []
}
```

Rules:

- `null` is preferred over invention.
- Preserve raw source text separately.
- Validate every response against a strict schema.
- Every result records model + prompt/schema version + analyzed timestamp.
- Batch size remains a tunable parameter. P0 uses small bounded batches first; a formal 5/10/20 comparison is deferred unless real pilot evidence shows omissions, cross-job contamination or rate-limit pressure.

## P0.5 Detail-page enrichment only when needed

Structured ATS adapters often already expose a description. Generic HTML discovery often does not.

Do not fetch every detail page indiscriminately.

```text
listing metadata/title
        ↓
LLM: cyber / non-cyber / needs_more_detail
        ↓
cyber or ambiguous + description missing
        ↓
fetch detail page
        ↓
full JobAnalyzer result
```

This keeps request volume low without reintroducing deterministic semantic filtering.

## P0.6 Persist complete cyber jobs

For every cybersecurity job, regardless of seniority, retain at minimum:

- company identity and source label;
- source/external job ID when available;
- ATS/requisition ID when available;
- original title;
- complete original description when obtainable;
- location/country/city/workplace values as provided;
- employment type as provided;
- source URL and apply URL;
- posted date when provided;
- `first_seen_at`;
- `last_seen_at`;
- payload/content hash computed from an application-owned canonical observation payload (see decision 0012);
- active/closed lifecycle state;
- AI analysis in a separate table/entity.

Do not duplicate an unchanged full description every scan. Existing `JobObservation.payload_changed` / hash behavior should be reused.

## P0.7 Reuse the lifecycle that already works

The current runtime already has important desired behavior:

- `first_seen_at` / `last_seen_at`;
- immutable observations;
- payload hash/change tracking;
- `missing_successful_scans`;
- closure advancement only for `SUCCESS` + `complete_snapshot` scans.

Keep it.

`seen_count` does **not** need a new column initially; it can be derived from observation count.

Initial closure policy:

```text
OPEN
  ↓ absent from successful complete snapshot
MISSING (1)
  ↓ absent from next successful complete snapshot
CLOSED
```

Failures, 403/429, incomplete snapshots or parser failures must not increment the missing streak.

## P0.8 Dashboard usable before automation

Implemented baseline: the dashboard now includes an `AI Cyber V2` view backed directly by AI-classified `SourceJob` rows rather than legacy deterministic `CanonicalJob` filters.

The first useful view should be intentionally simple:

- company;
- job title;
- role family/specialization;
- seniority;
- location;
- first seen;
- posted date if available;
- active/closed;
- source/apply link;
- skills.

Filters should include at least company, seniority, specialization, location and active/closed.

Do not block P0 on Telegram or automatic scheduling.

## P0 exit gate

A manual run over a meaningful portion of the 157 currently scannable core employers produces a browsable set of cybersecurity jobs of mixed seniority, with raw descriptions retained, AI analysis validated, duplicates controlled and lifecycle timestamps preserved.

---

# P1 — Make classification and coverage trustworthy

P1 improves the useful P0 rather than adding product surface area.

- Resolve/fix the remaining curated core portals.
- Benchmark JobAnalyzer batch sizes/models/prompts on a manually labeled set of **real discovered jobs**.
- Measure cyber precision/recall, especially ambiguous role names.
- Improve generic detail-page retrieval where it materially increases usable descriptions.
- Add direct old-job-URL verification as an optional final closure check where safe/cheap.
- Add AI-analysis reprocessing/versioning so a better model can re-analyze old cyber jobs without touching raw source records.
- Add coverage metrics: core employers resolved, scanned, successful, jobs discovered, jobs classified, cyber yield, AI failures.

P1 explicitly avoids automated employer ranking and broad new-company waves.

---

# P2 — Internship / early-career program intelligence

Separate from live-job scanning.

For each core employer, evidence-backed web research may collect:

- whether internships were historically observed;
- graduate/early-career programs;
- cyber-specific programs where supported;
- observed years;
- geography;
- evidence URLs and verification dates.

Use deterministic code for search/fetch/cache/evidence storage and LLMs for interpretation/extraction.

Do not ask a model from memory whether a company "usually hires interns" without evidence.

A historical opening calendar / seasonal cadence boost remains optional after this module proves useful.

---

# P3 — Automation and expansion

Only after P0/P1 are demonstrably useful:

- scheduled scans;
- cadence profiles independent from employer membership;
- Telegram notifications for newly seen jobs matching user-defined filters;
- optional seasonal cadence boosts;
- expand semantic domains from cybersecurity to AI and SWE;
- support multi-label overlap such as Cyber + AI, Cyber + SWE, or all three;
- retain manual LinkedIn CSV import only; no automated LinkedIn scraping.

## Expansion constraint

The database/schema should not hard-code "cybersecurity" as the only possible future domain. The pilot enables only cybersecurity, but AI/SWE can later be added as additional semantic domain labels without redesigning the ingestion core.

## Live validation checkpoint — 2026-09-02

Low-impact network canaries completed on three different hosts/stacks: KPMG (SuccessFactors), PayPal (Workday), and Mercedes-Benz (official HTML fallback). Five total HTTP requests returned 2xx with zero retries and no 403/429/challenge. Mercedes returned zero jobs despite current public vacancies, proving network health must be tracked separately from extraction/discovery health. Broad scanning remains deferred; next validation step is a one-batch, five-job LLM micro-canary against the disposable canary DB.

## P0 checkpoint update — end-to-end pilot completed 2026-09-02

The first five-employer end-to-end pilot is complete and accepted as architecture evidence. Broad scale-out is **not yet** approved because the pilot exposed title-only generic discoveries and one generic navigation false positive.

The active P0 sequence is now:

```text
small official listing scan
        ↓
PENDING_AI
        ↓
first AI pass
        ↓
CYBER / NEEDS_MORE_DETAIL with weak description
        ↓
selective official detail enrichment
        ↓
PENDING_AI again if detail changed
        ↓
AI re-analysis
        ↓
latest AI Cyber V2 view
```

Scale-out gate: validate this selective enrichment on the existing pilot DB first. Do not repeat already-successful pilot traffic merely to recreate state. Structured ATS detail endpoints should be added in order of measured need, beginning with Workday after the generic detail follow-up.
