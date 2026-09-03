# 0031 — Defer explicit AI-for-Security vs Security-of-AI taxonomy until domain expansion

**Status:** DEFERRED (P3)  
**Date:** 2026-09-02

## Observation
The P0 pilot classified Safe Security's `Principal Engineer - AI` as cybersecurity because the role builds AI systems powering cyber-risk products. That is reasonable for the current broad cyber corpus, but `AI for cybersecurity` and `security of AI systems` are different concepts.

## Decision
Do not expand the P0 schema merely to solve this future taxonomy question. When AI/SWE domains are enabled, add an explicit relationship dimension such as:

- AI_FOR_SECURITY
- SECURITY_OF_AI
- BOTH
- NONE

and keep multi-label domains (Cyber, AI, SWE) separate from this relationship.

## Why
This distinction will matter for later analysis but does not block the current cyber-only product. Adding it now would increase schema/prompt churn before the core acquisition pipeline is validated.
