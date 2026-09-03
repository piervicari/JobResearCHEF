# Live canary results — 2026-09-02

This file records empirical network tests performed from the user's Mac/network. It is evidence, not a guarantee of future access.

## Canary 01 — KPMG Italy / portal 69

Command shape:

```bash
uv run research-agent scan-canary --portal-id 69
```

Observed output:

```text
HTTP GET https://careers.kpmg.it/search/?q=&sortColumn=referencedate&sortDirection=desc&startrow=0 -> HTTP 200
status=SUCCESS
requests=1
retries=0
jobs=5
adapter=successfactors_rmk
semantic_processing=SKIPPED
```

Assessment: PASS.

Interpretation:

- the scanner completed this specific SuccessFactors RMK access with one request;
- no 401/403/429/challenge was observed;
- the tiny request budget was sufficient to recover five jobs;
- this result does not imply that other hosts or future higher-volume scans are safe.

## Next canary

Portal 514 — PayPal / Workday. Run dry-run first, then one live command if the target host/URL is correct.
