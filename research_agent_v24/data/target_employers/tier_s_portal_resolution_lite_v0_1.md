# Tier-S portal resolution lite v0.1

- Date: 2026-09-02
- Status: **RESEARCHED CANDIDATES — RUNTIME VALIDATION REQUIRED**
- Machine-readable companion: `tier_s_portal_resolution_lite_v0_1.csv`

## Purpose

Resolve only the remaining Tier-S discovery/runtime gaps before spending effort on generic company-universe waves.
A researched URL is not considered production-resolved until the runtime validates it and a versioned registry change is applied.

## Candidates

| Employer | Jobs source | Route | Confidence | Implementation action |
|---|---|---|---|---|
| OpenAI | https://openai.com/careers/search/ | Ashby-backed official search | HIGH | Update existing cluster `CG-7D3BBB5CBB`; validate with existing Ashby support / official page route. |
| Anthropic | https://www.anthropic.com/careers/jobs | Greenhouse-backed official jobs page | HIGH | Add target employer + portal; prefer Greenhouse structured route when discoverable. |
| Bloomberg | https://bloomberg.avature.net/careers/SearchJobs | Avature | MEDIUM_HIGH | Validate endpoint once at runtime before activation; do not mark healthy from research alone. |
| ENISA | https://www.enisa.europa.eu/careers | Official vacancy table | HIGH | Add custom/generic HTML route; vacancy rows and statuses are exposed directly. |
| NATO | https://www.nato.int/en/work-with-us/careers/vacancies | Official vacancies page | HIGH | Add core NATO portal; do not claim exhaustive coverage of independently recruiting NATO bodies. |
| European Space Agency | https://jobs.esa.int/ | Official recruiting site | HIGH | Add portal; let runtime detect ATS/structure instead of guessing it during resolution. |
| European Central Bank | https://talent.ecb.europa.eu/ | Official jobs site linked by ECB vacancies page | HIGH | Add portal; let runtime detect ATS/structure. |
| Check Point Software | https://careers.checkpoint.com/index.php?a=search&m=cpcareers | Custom HTML search | HIGH | Existing registry resolution is sufficient; fix/enable runtime route instead of re-resolving company ownership. |

## Evidence and rationale

- OpenAI's official search page lists open roles and links applications to `jobs.ashbyhq.com`; this is enough to classify the source as Ashby-backed without requiring Ashby knowledge as a resolution prerequisite.
- Anthropic's official jobs page is the source of truth; apply links point to Greenhouse.
- ENISA's official careers page directly exposes vacancies and statuses, so a bespoke ATS classification is unnecessary for V1.
- NATO's main vacancy page is official but some NATO bodies recruit independently; store that scope limitation explicitly rather than pretending one URL covers every NATO entity.
- ESA's official career material points to `jobs.esa.int`; ATS identification can happen during runtime discovery.
- ECB's official vacancies page points applicants to `talent.ecb.europa.eu`; ATS identification is not required to register the source.
- Bloomberg's Avature endpoint is plausible and corroborated but deserves one runtime validation before it enters the active registry.
- Check Point demonstrates why portal resolution and runtime scannability are separate states: the official jobs source exists, but the current runtime route needs fixing.

## Safety rule

Do not mutate the production registry merely because this file contains a URL. Registry activation requires:

1. successful HTTP/runtime validation;
2. confirmation that the returned content belongs to the intended employer/portal;
3. a versioned registry change with rollback support.
