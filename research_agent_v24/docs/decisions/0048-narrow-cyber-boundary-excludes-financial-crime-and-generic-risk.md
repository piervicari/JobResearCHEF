# 0048 — Narrow CYBER boundary excludes financial crime and generic risk/compliance

**Status:** Accepted / implemented in V24  
**Date:** 2026-09-02

## Decision

The semantic CYBER contract is narrowed in both high-recall triage and full JobAnalyzer prompts.

CYBER includes information/cybersecurity work such as security engineering, AppSec/product/cloud/infrastructure security, IAM, SOC/detection/IR/DFIR, threat intelligence, vulnerability management, security GRC, information-security risk and controls, technical privacy/security engineering, OT/ICS, offensive security, cryptography and AI security.

The following are NON_CYBER unless the posting itself demonstrates that the core work is genuinely information/cyber security:

- payment or merchant fraud operations;
- AML, KYC/KYB and financial crime;
- credit risk;
- generic enterprise or operational risk;
- generic regulatory/legal compliance;
- physical security;
- generic trust & safety, audit or privacy;
- generic software/AI/cloud engineering where security is incidental.

Boundary examples are explicit in the prompt: `Security GRC -> CYBER`, `Enterprise Risk Management -> NON_CYBER`, `Information Security Compliance -> CYBER`, `AML Compliance -> NON_CYBER`.

Prompt versions advance to `cyber-triage-v2` and `cyber-job-v4` so the semantic contract is auditable and does not silently reuse an older definition.

## Why

The Stripe V23 probe showed good technical discovery but over-broad semantics: MiniMax classified payment fraud, merchant fraud, AML/financial crime and generic enterprise risk/compliance roles as cybersecurity. Those roles may be relevant to a candidate, but relevance is not the same as membership in a cybersecurity dataset.

## Alternatives rejected

- **Regex/keyword exclusions:** rejected because they would make semantic membership deterministic and brittle, contrary to the project design.
- **Keep broad CYBER and filter in the dashboard:** rejected because it contaminates the dataset and downstream analytics.
- **Add a second specialist agent:** rejected as unnecessary; a clearer contract is simpler and cheaper.

## Trade-offs

The stricter boundary may create occasional false negatives for unusual fraud/security hybrid roles. Triage therefore remains high-recall: genuinely ambiguous or technical-security fraud roles continue to full analysis. The final decision remains LLM-semantic rather than keyword based.
