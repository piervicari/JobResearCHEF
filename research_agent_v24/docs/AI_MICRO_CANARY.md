# AI Micro-Canary — First Live Structured Batch

Purpose: validate the real LLM route, prompt, schema and classifications on five already-local jobs without touching any career site or the main database.

## Preconditions

- Use the disposable DB created by `prepare-canary-db`.
- Put `GEMINI_API_KEY` and `OPENROUTER_API_KEY` in `.env`.
- Do not put quotes around the keys unless the key itself contains spaces (normally it does not).
- `.env` is ignored by packaging/version control and is not a backup file.

## Step 0 — credential/config preflight

```bash
uv run research-agent llm-preflight
```

Expected: `google_key_present: true` and `openrouter_key_present: true`. This command only checks the local environment and makes zero external requests. Project `.env` is loaded automatically; explicit shell environment variables still take precedence.

## Step 1 — zero-request preview

```bash
uv run research-agent analyze-pending \
  --database-url sqlite:///data/canary/research_agent_canary.db \
  --limit 5 \
  --batch-size 5 \
  --dry-run
```

Expected: five Apiiro jobs and exactly one planned LLM request. No career-site request is ever made by `analyze-pending`.

## Step 2 — one live batch

```bash
uv run research-agent analyze-pending \
  --database-url sqlite:///data/canary/research_agent_canary.db \
  --limit 5 \
  --batch-size 5
```

The configured `job_analysis` route is used. Normal success should use Gemini 3.7 Flash medium. Fallbacks are invoked only on the configured failure conditions.

## Step 3 — inspect results locally

```bash
uv run research-agent show-ai-results \
  --database-url sqlite:///data/canary/research_agent_canary.db \
  --limit 5
```

No external requests occur in this step.

## What to evaluate manually

The first five jobs intentionally include both ambiguous and obvious negatives:

- AI Engineer — ambiguous; read description before deciding;
- AI Research Engineer, Security — expected strong cyber/AI candidate;
- Customer Success Manager — expected non-cyber unless description materially contradicts the title;
- Customer Success Manager (EMEA) — same;
- Director of Sales — expected non-cyber unless description materially contradicts the title.

Do not judge the system only by the binary cyber label. Inspect role family, specialization, seniority, experience and extracted skills, and check that the model did not invent unsupported requirements.

## Stop conditions

Do not increase batch size or job count if:

- any job ID is skipped/duplicated;
- structured output validation fails repeatedly;
- obvious Sales/Customer Success roles are labeled cyber without strong description evidence;
- the model invents skills/years not present in the posting;
- fallback unexpectedly activates on a normal successful primary call.


## Live progress behavior (V10)

Live analysis now emits progress before each provider call. A normal MEDIUM batch must never appear silent for an unbounded period: each line shows the model, fallback index and effective timeout. `job_analysis` no longer retries Gemini 3.7 Flash after a transient error; it falls through to the next target. The route now remains free-only and falls from the Google models directly to `minimax/minimax-m3:free` on OpenRouter.


## Logged test runner (current recommended workflow)

Run the complete isolated AI micro-canary with one command:

```bash
./scripts/run_ai_micro_canary.sh
```

It resets the canary DB, performs preflight + dry-run + live 5-job batch, then prints full AI results.
All stdout/stderr (including 15-second LLM heartbeats and fallback telemetry) is also written to:

```text
output/test_runs/ai_micro_canary_<timestamp>.log
```

Upload that log for review instead of copying terminal output. The script never prints API-key values.

As of decision 0023, Gemini 3.7 Flash is temporarily disabled. The active normal route is Gemini 3.6 Flash → MiniMax M3 :free.
