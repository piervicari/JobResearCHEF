# P0 end-to-end pilot analysis — 2026-09-02

Source evidence: `p0_end_to_end_pilot_20260902-140011.log`.

## Outcome

The V2 architecture works end-to-end but broad rollout is gated by source-detail quality.

### Network

- 5 employers
- 8 HTTP requests
- 8 HTTP 200
- 0 retries
- 0 403/429/challenge
- 36 discovered jobs

This is positive evidence for the conservative network profile, not proof that every core portal is safe/parseable.

### LLM

- 36 jobs
- batch size 10
- 4 batches
- 5 actual LLM attempts total
  - Gemini 3.6 Flash: 4 attempts, 3 successes, 1 HTTP 503
  - MiniMax M3 :free: 1 fallback attempt, 1 success
- 4 CYBER
- 24 NON_CYBER
- 8 NEEDS_MORE_DETAIL
- 0 jobs left pending

Fallback therefore behaved correctly: a provider-capacity error did not require re-scanning a career site and did not lose the batch.

## Important quality findings

### 1. Title-only generic discoveries are insufficient for the product goal
Detectify/Wazuh generic HTML entries can have zero description. The AI can still classify obvious titles, but skills/experience/degree fields are empty. Because the product is also intended for skill reverse-engineering, `CYBER` does **not** mean enrichment can stop when source evidence is incomplete.

### 2. NEEDS_MORE_DETAIL mostly identifies acquisition gaps
Eight jobs were ambiguous under available evidence. The correct next operation is targeted official detail acquisition, not prompt tuning or deterministic keyword rules.

### 3. Generic navigation false positive
Trellix generated `Find Jobs` as one pseudo-vacancy. Current official Trellix listings point to Workday, so the better fix is registry correction + generic navigation exclusion, not portal-specific generic parsing.

### 4. AI taxonomy nuance to revisit later
`Principal Engineer - AI` at Safe Security was classified as cyber because the role builds AI systems powering cybersecurity products. This is reasonable for the current broad cyber dataset, but future AI/SWE expansion should distinguish **AI for Security** from **Security of AI / AI Security** rather than using one overloaded label.

## Decision
Proceed to a five-job selective detail-enrichment follow-up using the **existing pilot database**, then re-analyze only changed rows. Do not repeat the already-successful listing scan merely to recreate the same state.
