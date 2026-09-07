# ATS & Capability Crosscheck (concise technical matrix)

Evidence classes: LIVE_FIXTURE (our saved wire responses),
HISTORIC (legacy adapter fixtures), EXTERNAL_REFERENCE (public code/docs
read offline, never executed), CURRENT_LIVE_VERIFIED (always false here).

## ATS matrix (JobResearCHEF × external)

| ATS | JobResearCHEF | ats-scrapers | ats-jobs | CareerScout | New info? |
|---|---|---|---|---|---|
| Greenhouse | adapter+fixture | scraper+6k seeds | endpoint | template | NONE |
| Lever | adapter+fixture | scraper+seeds | endpoint | template | NONE |
| Ashby | adapter+fixture | scraper+3.4k seeds | endpoint | template | NONE |
| Workday | adapter+fixture | scraper+3.5k seeds + cap-2000 note | endpoint+offset POST | template | MINOR (cap-2000 reporting quirk) |
| SmartRecruiters | adapter+fixture | scraper+seeds | offset endpoint | template | NONE |
| SuccessFactors | adapter+fixture | scraper+1.4k seeds | — | — | NONE |
| Oracle | adapter+fixture | scraper+seeds | — | — | NONE |
| Phenom | adapter+fixture | scraper+99 seeds | — | — | NONE |
| Avature | adapter+fixture | scraper+127 seeds (+browserbase fallback noted, rejected) | — | — | NONE |
| Radancy | adapter+fixture | code paths, no CSV | — | — | NONE |
| Eightfold | spec (NVIDIA/MS) | scraper+84 seeds, `start=`+`data.count` | — | — | MINOR (independent offset confirmation) |
| Apple | NEEDS_EXTENSION | scraper: CSRF→search→loader-state detail | — | — | IMPORTANT (confirms bootstrap + split qualifications; see below) |
| Google | CODE_ONLY (stale RPC) | HTML listing ?page=N + detail HTML | — | — | IMPORTANT (CANDIDATE_SIMPLER_PATH) |
| Meta | UNRESOLVED | cloakbrowser GraphQL (rejected runtime) | — | — | MINOR (protocol shape only) |
| Workable/BambooHR/Breezy/Recruitee/Teamtailor/Personio/Rippling/iCIMS/Taleo/UKG… | not supported | scrapers + seeds | some endpoints | some templates | NONE (no universe demand now) |

IMPORTANT details: (1) Apple loader-state detail carries
description/minimumQualifications/preferredQualifications as separate JSON
fields — second independent implementation of our split-qualifications
need. (2) Google HTML path (stable aria-label anchors, icon-chip
locations, page-number, per-job detail pages) sidesteps our stale
`r06xKb` RPC with no opaque IDs — candidate path when Google is scheduled.

## Capability crosscheck

| Capability | Existing evidence | External evidence | Confidence ↑? |
|---|---|---|---|
| offset pagination | LIVE (Eightfold/Beesite/SR) | Eightfold `start=`, SR `offset=`, WD `offset=` | yes (3rd implementations) |
| page_number | LIVE (Apple) + legacy | Google `?page=N` HTML | yes |
| single_request/unpaginated | LIVE (revoked CF) + legacy ×3 | 9 single-shot boards in ats-jobs | yes |
| load_more/next_link | legacy ×3 | — | no |
| bootstrap request | LIVE (Apple) + legacy ×2 | Apple CSRF (2nd impl) | yes |
| cookie/session persistence | LIVE (Apple) | Apple single-session fetcher | yes (minor) |
| multi-field text composition | LIVE (Amazon, archived) | Apple desc+min+pref assembly | yes (same need, 2nd shape) |
| separate qualifications | LIVE (Amazon) | Apple min/prefQualifications fields | yes |
| HTML embedded JSON | legacy ×2 | Apple `__loaderData__`, Meta JSON-LD | yes |
| HTML entity decode | LIVE (Greenhouse) | — (handled in their html utils, same one-liner) | no |
| form encoded POST | CODE_ONLY (Google/Meta) | Google uses plain GET; Meta needs browser tokens | no (weakens form-RPC case for Google) |
| positional arrays | CODE_ONLY (Google RPC) | Google HTML needs none | no (simpler path avoids it) |
| persisted/opaque op IDs | CODE_ONLY | Google HTML needs none; Meta doc_id browser-issued | partial (Meta confirms the hard case) |
| HTML detail extraction | legacy (detail_enrichment) | Google detail meta tags, Apple loader JSON | yes (minor) |
| URL/path locale | legacy (SF locale path) | Google `hl=` query | no |
| multi-location extraction | legacy ×3 + v0.1 template | Google icon chips,ats-jobs location strings | no (covered) |

Genuinely new capabilities: none (all external observations map onto the
existing registry rows). Speculative additions rejected: GraphQL-as-primitive
(Meta needs browser tokens — no deterministic primitive exists), parallel
provider-probing discovery (ats-jobs discover.js is reference-only),
residential-proxy/stealth execution (rejected outright).
