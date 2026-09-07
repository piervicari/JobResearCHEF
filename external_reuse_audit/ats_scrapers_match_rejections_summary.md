# Rejections / ambiguous pairs summary (not stored as rows)

Total rejected pairs: 379. Nothing below was written to the candidate CSVs.
No live check was performed on any of them.

## Generic-name rejections: 15 pairs

External normalized name ≤2 chars (e.g. two-letter startup names) matching an
internal company. Too weak for even CANDIDATE; would need operator evidence
that does not exist offline.

## Multi-internal-match rejections: 364 pairs

One external (normalized-name, ATS, slug, URL) tuple matching >1 internal
company — typically shared brand/parent names (group ↔ subsidiary, e.g. a bank
group and its regional entities, or common words like "Alliance"/"Apex" used
by unrelated firms). When one of the contenders ALSO has domain/URL evidence
it is emitted as HIGH and the others stay rejected; otherwise all stay out.
Same brand, different entities, is the dominant cause — exactly the §4 case
for never auto-binding.

## Known residual risks inside the ACCEPTED sets (documented, not silent)

- Single-word NAME_EXACT candidates (e.g. "Planet", "Bolt", "Shift") may be
  different entities sharing a word; they are CANDIDATE-to-inspect by design.
- SLUG_PLUS_NAME uses name containment (min-length guarded); regional entities
  can resolve to a global group board (Vodafone Romania → Vodafone) — kept as
  distinct rows, operator must pick the binding.
- Only 1,277/12,503 universe rows (≈10%) carry any resolved domain/portal, so
  HIGH recall is structurally capped until portal resolution advances; this is
  a data limit, not a matcher defect.
- A first script run produced 3,448 false ashby SLUG rows (first DNS label
  `jobs` matched against `jobs.*` board hosts); root-caused, fixed with
  registrable-domain tokens + generic-subdomain stoplist, and outputs were
  regenerated from scratch. Final CSVs contain zero rows from that run
  (verified: no `jobs`-token SLUG basis remains).
