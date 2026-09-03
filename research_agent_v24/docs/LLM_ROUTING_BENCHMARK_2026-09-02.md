# LLM routing benchmark basis — 2026-09-02

Purpose: document the external benchmark evidence used to choose initial Research Agent task routes.

Important: these are **general model benchmarks**, not accuracy measurements on Research Agent job posts. The final model/batch choice must still be validated on a manually labelled real-job golden set.

| Model / reasoning | Artificial Analysis Intelligence Index | Output speed (approx.) | Cost per AA Intelligence task | Intended use here |
|---|---:|---:|---:|---|
| Gemini 3.7 Flash high | 56 | ~290-324 tok/s | ~$0.40 | HARD primary |
| Gemini 3.7 Flash medium | 53 | ~287-318 tok/s | ~$0.26 | MEDIUM primary |
| Gemini 3.7 Flash low | 51 | ~308-315 tok/s | ~$0.16 | EASY/light fallback candidate |
| Gemini 3.6 Flash high | 52 | ~168 tok/s | ~$0.34 | Google fallback |
| GLM-5.3-Flash | 57 | ~42-49 tok/s on first-party AA measurement; provider-dependent | paid | **Excluded by free-only policy (0021)** |
| MiniMax-M3 | 45 | ~116-150 tok/s depending provider measurement | ~$0.14 | Current primary via OpenRouter free variant when available |
| Gemini 3.5 Flash-Lite | 37 | ~346 tok/s | ~$0.10 | JSON repair / low-risk mechanical work |

## Sources

Artificial Analysis, retrieved 2026-09-02:

- https://artificialanalysis.ai/models/releases/gemini-3-7-flash
- https://artificialanalysis.ai/models/gemini-3-7-flash
- https://artificialanalysis.ai/models/gemini-3-6-flash
- https://artificialanalysis.ai/models/glm-5-3-flash
- https://artificialanalysis.ai/models/minimax-m3
- https://artificialanalysis.ai/models/gemini-3-5-flash-lite

## Interpretation

The useful result is not simply "pick the highest number".

- Normal job analysis is semantically non-trivial but repetitive and structured. Gemini 3.7 Flash **medium** is a better default than paying the reasoning/latency cost of `high` on every batch.
- Ambiguous titles/descriptions are explicitly escalated to Gemini 3.7 Flash **high**.
- GLM-5.3-Flash benchmarks well but is excluded from routing because the current project policy is free-only. It remains benchmark context only, not an executable fallback.
- MiniMax-M3 is the final free resilience fallback, not the semantic gold standard for hard cases.
- Flash-Lite is deliberately restricted to mechanical JSON/schema repair and optional future light classification.

## Required project-specific benchmark

Before large AI processing, test at least:

```text
batch size: 5 / 10 / 20
models: MEDIUM primary + fallbacks
sample: real SourceJob rows manually labelled
metrics:
  cyber false negatives (highest priority)
  cyber precision
  seniority extraction
  years-of-experience extraction
  skills extraction quality
  omitted/duplicated job IDs
  invalid JSON/schema rate
  tokens/job
  latency/job
  fallback frequency
```

For this project, false negatives on cyber relevance matter more than a small amount of non-cyber noise.

## Operational override — 2026-09-02

General benchmark rankings are not the only routing criterion. On the actual 5-job Research Agent micro-canary, Gemini 3.7 Flash repeatedly showed poor availability/latency (including a full 300s read timeout), while Gemini 3.6 Flash completed the same batch in ~29.6s. Decision 0023 therefore temporarily disables Gemini 3.7 Flash from every active route.

The subsequent P0 pilot/detail runs added stronger operational evidence: Gemini 3.6 Flash repeatedly consumed long waits or returned 503, while MiniMax M3 completed successful fallback batches in single-digit seconds when available. A later M3 attempt hit an upstream shared-pool 429 with an explicit `Retry-After: 60`. Decision 0038 therefore changes the operational route to favor the observed fast free path while handling temporary free-pool scarcity explicitly.

Current normal route:

```text
MiniMax M3 :free (medium, 300s; one retry only with explicit Retry-After, max wait 90s)
→ MiniMax M2.7 :free (medium, 300s; resilience only)
→ Gemini 3.6 Flash (high, 300s; final cross-provider fallback)
```

MiniMax M2.7 is intentionally only a resilience fallback: it is older/weaker than M3 in current Artificial Analysis results. Re-enable 3.7 only after controlled workload-specific evidence, not because of benchmark rank alone.
