# Research Agent — Tier-S ATS / Career Backend Mapping

**Created:** 2026-09-02  
**Scope:** operational census of the highest-priority employers before building any new resolver/adapter.  
**Artifact policy:** this file is intentionally **standalone and outside the supplied Research Agent ZIP**. It is the working mapping ledger and can be updated independently of code releases.

## Why this file exists

Before spending LLM/tool-call budget on autonomous portal resolution, classify each Tier-S employer into one of three paths:

- **FAST_PATH** — current Research Agent ZIP already has the required ATS adapter; derive/confirm tenant token, then probe.
- **ADAPTER_NEEDED** — platform/backend is identifiable but not supported in the supplied ZIP; build one reusable platform adapter.
- **RESOLVER_NEEDED** — custom/proprietary backend or backend not yet proven; investigate network/API/RPC before coding.

The supplied ZIP currently registers structured adapters for:

`Greenhouse`, `Lever`, `Ashby`, `SmartRecruiters`, `Radancy`, `SuccessFactors RMK`, `Workday`, `Phenom`, `Oracle Recruiting Cloud`, `Avature`.

`GenericOfficialHtmlAdapter` exists only as fallback and does **not** count as a verified structured integration.

---

## Status vocabulary

- **VERIFIED** — first-party/ATS evidence is strong enough to treat the platform mapping as established.
- **PROBABLE** — strong signal, but backend/API contract still needs a direct probe before we freeze the mapping.
- **UNKNOWN** — career frontend is known but underlying operational source is not yet established.

For `FAST_PATH`, this file only means **platform mapping is ready for a controlled probe**. It does not mean catalog completeness/CYBER recall has already passed.

---

## Tier-S mapping — Batch 1

| Priority | Employer | Canonical careers surface | Operational ATS / backend | Confidence | Adapter in supplied ZIP | Path | Next action |
|---:|---|---|---|---|---:|---|---|
| baseline | Stripe | `https://stripe.com/careers/search` | Greenhouse, board token `stripe` | VERIFIED | Yes | FAST_PATH / already validated | Keep as reference fixture |
| 1 | Google | `https://www.google.com/about/careers/applications/jobs/results` | Custom Google Careers frontend / structured RPC family; not an ATS currently present in supplied ZIP | VERIFIED at platform-family level; RPC contract requires project implementation | No | ADAPTER_NEEDED | Implement/reuse Google structured RPC adapter, then full probe |
| 2 | Microsoft | `https://careers.microsoft.com/` | Microsoft Careers custom frontend; underlying operational backend not frozen here | UNKNOWN | No proven match | RESOLVER_NEEDED | Inspect network/API first; do not assume Eightfold without direct evidence |
| 3 | Amazon / AWS | `https://www.amazon.jobs/` | Amazon Jobs proprietary/custom | VERIFIED as custom Amazon Jobs surface | No | RESOLVER_NEEDED | Discover structured search/detail endpoints; AWS shares Amazon Jobs |
| 4 | Meta | `https://www.metacareers.com/jobs/` | Meta Careers proprietary/custom | PROBABLE | No | RESOLVER_NEEDED | Inspect current search/detail network contract |
| 5 | Apple | `https://jobs.apple.com/` | Apple Jobs proprietary/custom; official search exposes stable role numbers and rich server-visible listings | VERIFIED as custom Apple surface | No | RESOLVER_NEEDED | Find first-party structured search/detail datasource before HTML parsing |
| 6 | NVIDIA | `https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite` | Workday (`wd5`) | VERIFIED | **Yes — Workday** | **FAST_PATH** | Derive tenant/site config and run Workday probe |
| 7 | Cloudflare | `https://www.cloudflare.com/careers/jobs/` | Greenhouse operational board (`cloudflare`) behind vanity careers surface | VERIFIED | **Yes — Greenhouse** | **FAST_PATH** | Probe Greenhouse board token `cloudflare`; compare against vanity site |
| 8 | Palo Alto Networks | `https://jobs.paloaltonetworks.com/en/search_jobs` | Custom/hosted career search; Phenom-style signatures are plausible but not frozen without direct backend evidence | PROBABLE custom / platform TBD | Maybe (Phenom adapter exists) | RESOLVER_NEEDED first | Inspect page/network; if Phenom confirmed, convert immediately to FAST_PATH |
| 9 | CrowdStrike | `https://crowdstrike.wd5.myworkdayjobs.com/crowdstrikecareers` | Workday (`wd5`) | VERIFIED | **Yes — Workday** | **FAST_PATH** | Derive tenant/site config and run Workday probe |
| 10 | Cisco | `https://jobs.cisco.com/jobs/SearchJobs/` | Cisco Jobs custom search surface; underlying platform not frozen | PROBABLE custom | No proven match | RESOLVER_NEEDED | Inspect network/API; avoid inferring ATS from URL shape alone |
| 11 | Datadog | `https://careers.datadoghq.com/` | Greenhouse operational board (`datadog`) behind vanity careers surface | VERIFIED | **Yes — Greenhouse** | **FAST_PATH** | Probe Greenhouse board token `datadog`; verify catalog parity |
| 12 | Palantir | `https://jobs.lever.co/palantir` | Lever | VERIFIED | **Yes — Lever** | **FAST_PATH** | Run Lever probe; no new adapter expected |
| 13 | OpenAI | `https://jobs.ashbyhq.com/openai` | Ashby | VERIFIED | **Yes — Ashby** | **FAST_PATH** | Run Ashby probe; no new adapter expected |
| 14 | Anthropic | `https://www.anthropic.com/careers/jobs` | Greenhouse operational board (`anthropic`) behind first-party careers frontend | VERIFIED | **Yes — Greenhouse** | **FAST_PATH** | Probe Greenhouse board token `anthropic`; compare against Anthropic frontend |

---

## First result

Among the first 14 priority employers:

- **7 are already clear FAST_PATH candidates:** NVIDIA, Cloudflare, CrowdStrike, Datadog, Palantir, OpenAI, Anthropic.
- **Google** is a known custom structured-platform case but needs an adapter not present in the supplied ZIP.
- **Microsoft, Amazon/AWS, Meta, Apple, Cisco** currently belong in the resolver queue.
- **Palo Alto Networks** should get a very cheap fingerprint/network check first because, if the suspected hosted-platform family matches an adapter already present (e.g. Phenom), it may immediately move to FAST_PATH.

This means we should **not** send every Tier-S employer through a full LLM resolver. The pipeline should be:

```text
Tier-S employer
  -> deterministic ATS fingerprint/census
     -> supported ATS       -> FAST_PATH probe
     -> known unsupported   -> build reusable adapter once
     -> unknown/custom      -> resolver investigation
```

---

## Evidence / source ledger — Batch 1

The source ledger is deliberately kept here so the mapping remains auditable even when the code ZIP changes.

### Stripe
- Canonical careers: https://stripe.com/careers/search
- Operational source established in project: `https://boards-api.greenhouse.io/v1/boards/stripe/jobs?content=true`

### Google
- Official careers results: https://www.google.com/about/careers/applications/jobs/results
- Project status: custom Google Careers structured frontend/RPC is the intended next integration; not present in the supplied V23 adapter registry.

### Microsoft
- Official careers: https://careers.microsoft.com/v2/global/en/home.html
- Current mapping deliberately remains `UNKNOWN` at backend level until direct network/API evidence is captured.

### Amazon / AWS
- Official global jobs: https://www.amazon.jobs/en
- AWS careers are surfaced through Amazon Jobs: https://www.amazon.jobs/content/en/teams/amazon-web-services

### Meta
- Official careers jobs: https://www.metacareers.com/jobs/
- Backend remains to be directly fingerprinted.

### Apple
- Official jobs search: https://jobs.apple.com/
- Example search pages expose stable role numbers and result counts directly on first-party Apple pages.

### NVIDIA
- Workday site: https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite

### Cloudflare
- First-party careers: https://www.cloudflare.com/careers/jobs/
- Greenhouse board identity: https://job-boards.greenhouse.io/cloudflare

### Palo Alto Networks
- First-party job search: https://jobs.paloaltonetworks.com/en/search_jobs
- Backend/platform confirmation intentionally pending a direct network inspection.

### CrowdStrike
- Workday site: https://crowdstrike.wd5.myworkdayjobs.com/crowdstrikecareers

### Cisco
- First-party job search: https://jobs.cisco.com/jobs/SearchJobs/
- Backend/platform confirmation intentionally pending.

### Datadog
- First-party careers: https://careers.datadoghq.com/
- Greenhouse board identity: https://job-boards.greenhouse.io/datadog

### Palantir
- Lever board: https://jobs.lever.co/palantir

### OpenAI
- Ashby board: https://jobs.ashbyhq.com/openai

### Anthropic
- First-party careers: https://www.anthropic.com/careers/jobs
- Greenhouse board identity: https://job-boards.greenhouse.io/anthropic

---

## Next batch / working rule

Continue this file before writing a general autonomous resolver. The immediate high-ROI sequence is:

1. run/validate the 7 FAST_PATH Tier-S mappings with existing adapters;
2. do the one-shot fingerprint check on Palo Alto Networks;
3. resolve the genuinely custom queue: Microsoft -> Amazon/AWS -> Meta -> Apple -> Cisco;
4. every time a reusable platform adapter is added, reclassify all remaining employers before invoking the resolver again.

The mapping file should remain outside release ZIPs until we decide its schema is stable enough to import into the project as structured data.

---

## Tier-S mapping — Batch 2

This batch extends the census into high-value cybersecurity vendors, aerospace/defense, infrastructure/security SaaS and payments. As in Batch 1, a FAST_PATH classification only means that the ATS family is already supported by the supplied Research Agent ZIP; employer-level catalog verification still requires a controlled probe.

| Priority | Employer | Canonical careers surface | Operational ATS / backend | Confidence | Adapter in supplied ZIP | Path | Next action |
|---:|---|---|---|---|---:|---|---|
| 15 | SpaceX | `https://www.spacex.com/careers/` | Greenhouse, board token `spacex` | VERIFIED | **Yes — Greenhouse** | **FAST_PATH** | Probe Greenhouse board `spacex`; verify first-party career parity |
| 16 | Anduril Industries | `https://www.anduril.com/careers/` / `https://www.anduril.com/open-roles` | Greenhouse, board token `andurilindustries` | VERIFIED | **Yes — Greenhouse** | **FAST_PATH** | Probe board `andurilindustries`; compare against current Anduril open-roles surface |
| 17 | Blue Origin | `https://www.blueorigin.com/careers` | Workday `blueorigin.wd5.myworkdayjobs.com/BlueOrigin` | VERIFIED | **Yes — Workday** | **FAST_PATH** | Derive Workday tenant/site tuple and run structured probe |
| 18 | Okta | `https://www.okta.com/company/careers/` | Greenhouse, board token `okta` | VERIFIED | **Yes — Greenhouse** | **FAST_PATH** | Probe Greenhouse board `okta`; compare against vanity career frontend |
| 19 | Vanta | `https://www.vanta.com/careers` | Ashby, tenant/slug `vanta` | VERIFIED | **Yes — Ashby** | **FAST_PATH** | Run Ashby probe; no new adapter expected |
| 20 | Visa | `https://corporate.visa.com/en/careers.html` | SmartRecruiters (`careers.smartrecruiters.com/Visa/...`) | VERIFIED at ATS-family level | **Yes — SmartRecruiters** | **FAST_PATH** | Resolve company identifier used by existing SmartRecruiters adapter and probe full catalog |
| 21 | SentinelOne | `https://www.sentinelone.com/careers/` | Greenhouse board identity `sentinelone` appears strongly evidenced by current ATS directories, but first-party redirect/network proof not captured in this batch | PROBABLE | **Yes — Greenhouse** | FAST_PATH candidate | One cheap direct board/API check; if live and canonical job URLs line up, upgrade to VERIFIED |
| 22 | Tesla | `https://www.tesla.com/careers/search/` | Tesla proprietary/custom careers search; stable Tesla job URLs visible on first-party site | VERIFIED as custom Tesla surface | No proven structured adapter match | **RESOLVER_NEEDED** | Discover first-party search/detail API or embedded datasource; avoid generic HTML unless no structured source exists |
| 23 | Fortinet | `https://www.fortinet.com/corporate/careers` | Fortinet custom/hosted careers flow; no supported ATS family proven in this batch | UNKNOWN / custom surface verified | No proven match | **RESOLVER_NEEDED** | Follow `Explore Careers at Fortinet` into operational jobs surface and fingerprint network/backend |
| 24 | Zscaler | `https://www.zscaler.com/careers` | Zscaler first-party careers search; backend family not yet proven from first-party evidence | UNKNOWN | No proven match yet | **RESOLVER_NEEDED** | Inspect search requests/redirects; only map to SmartRecruiters/other ATS after direct evidence |

### Batch-2 high-confidence result

Of these 10 employers:

- **6 are high-confidence FAST_PATH:** SpaceX, Anduril, Blue Origin, Okta, Vanta, Visa.
- **1 is a very likely FAST_PATH pending a single cheap proof:** SentinelOne -> Greenhouse.
- **3 remain genuine resolver work:** Tesla, Fortinet, Zscaler.

That means the cumulative first 24 employers currently look roughly like:

```text
14 existing Batch-1 Tier-S targets
+ 10 Batch-2 targets

clear FAST_PATH            = 13
FAST_PATH candidate        = 1
known custom adapter case  = 1   (Google; implemented in V24, but not in supplied V23 ZIP)
resolver/custom queue      = 9
```

The practical implication is stronger than after Batch 1: **over half of the employers examined so far can likely skip autonomous portal-resolution reasoning entirely and go straight to an existing structured adapter + controlled employer probe.**

---

## Evidence / source ledger — Batch 2

### SpaceX
- First-party careers: https://www.spacex.com/careers/
- Current 2026 job postings repeatedly resolve to `https://job-boards.greenhouse.io/spacex/jobs/...`.
- Greenhouse board/API identity: `spacex`.

### Anduril Industries
- First-party careers: https://www.anduril.com/careers
- First-party open roles: https://www.anduril.com/open-roles
- Current postings resolve to `https://job-boards.greenhouse.io/andurilindustries/jobs/...`.
- Greenhouse board/API identity: `andurilindustries`.

### Blue Origin
- First-party careers: https://www.blueorigin.com/careers
- Current operational job URLs use: `https://blueorigin.wd5.myworkdayjobs.com/BlueOrigin/...`
- Workday tuple observed in current postings: `wd5 | blueorigin | BlueOrigin`.

### Okta
- First-party careers: https://www.okta.com/company/careers/
- Current operational postings resolve to `https://job-boards.greenhouse.io/okta/jobs/...`.
- Greenhouse board identity: `okta`.

### Vanta
- First-party careers: https://www.vanta.com/careers
- Current operational postings resolve to `https://jobs.ashbyhq.com/vanta/...`.
- Ashby slug: `vanta`.

### Visa
- First-party careers: https://corporate.visa.com/en/careers.html
- Visa recruiting/program pages are hosted on `https://careers.smartrecruiters.com/Visa/...`.
- This is sufficient to map the ATS family to SmartRecruiters; the exact identifier expected by our adapter still needs a zero/low-cost probe.

### SentinelOne
- First-party careers: https://www.sentinelone.com/careers/
- Current external ATS directories identify `https://boards.greenhouse.io/sentinelone` / Greenhouse as the operational board.
- Because this batch did not capture a first-party apply redirect or live board response directly, status remains PROBABLE rather than VERIFIED.

### Tesla
- First-party search: https://www.tesla.com/careers/search/
- First-party Tesla search exposes thousands of roles and stable paths such as `/careers/search/job/<id>`.
- No supported ATS signature has been established yet; treat as custom until network/API discovery proves otherwise.

### Fortinet
- First-party careers: https://www.fortinet.com/corporate/careers
- Current site exposes an `Explore Careers at Fortinet` flow but this batch did not establish a supported structured ATS family.

### Zscaler
- First-party careers/search: https://www.zscaler.com/careers
- Search is embedded in the first-party careers experience; this batch deliberately leaves the operational backend UNKNOWN until direct request inspection.

---

## Revised execution strategy after Batch 2

Do **not** build the general autonomous resolver yet. The higher-ROI order is now:

1. **Bulk fingerprint the remaining CORE employers** using cheap URL/redirect/ATS-signature checks.
2. Put every verified Greenhouse/Workday/Lever/Ashby/SmartRecruiters/etc. employer into a `READY_TO_PROBE` queue.
3. Run reusable platform probes in batches by ATS family, while keeping employer-level PASS/FIX independent.
4. Reserve LLM/browser resolver work for the shrinking `UNKNOWN/CUSTOM` queue.
5. Every new reusable adapter must trigger a reclassification pass over the unresolved queue before the next custom investigation.

A likely future structured representation of this ledger should contain at least:

```text
employer
corporate_cluster_id
priority_tier
canonical_careers_url
operational_jobs_url
ats_family
ats_tenant_or_token
confidence
adapter_supported
resolution_path
last_verified_at
evidence_urls
notes
```

For now the Markdown ledger remains authoritative and intentionally outside release ZIPs.

---

## Tier-S mapping — Batch 3

This batch moves into finance, automotive and aerospace/defense. The same rule still applies: **do not infer platform equivalence from branding alone**. In particular, Oracle Recruiting Cloud, Oracle Taleo and IBM/Kenexa BrassRing are different integration families even if all of them are enterprise recruiting systems.

| Priority | Employer | Canonical careers surface | Operational ATS / backend | Confidence | Adapter in supplied ZIP | Path | Next action |
|---:|---|---|---|---|---:|---|---|
| 25 | JPMorgan Chase | `https://careers.jpmorgan.com/` | Oracle Recruiting Cloud / Oracle Fusion Candidate Experience (`jpmc.fa.oraclecloud.com`, sites such as `CX_1001`, `CX_1002`) | VERIFIED | **Yes — Oracle Recruiting Cloud** | **FAST_PATH** | Resolve all relevant public site IDs/tenants and run Oracle catalog probe; preserve cross-site dedup by requisition/job ID |
| 26 | Goldman Sachs | `https://www.goldmansachs.com/careers` -> `https://higher.gs.com/results` | Goldman Sachs proprietary `higher.gs.com` jobs frontend; underlying structured backend not frozen | VERIFIED as custom first-party surface; backend UNKNOWN | No proven match | **RESOLVER_NEEDED** | Inspect `higher.gs.com` network/search/detail requests before building anything |
| 27 | Morgan Stanley | `https://www.morganstanley.com/careers/career-opportunities-search` | First-party Morgan Stanley custom search UI; backend not established in this batch | VERIFIED as custom first-party surface; backend UNKNOWN | No proven match | **RESOLVER_NEEDED** | Inspect search/guided-search requests and identify stable source-job identity/API |
| 28 | UBS | `https://www.ubs.com/global/en/careers/search-jobs.html` -> `https://jobs.ubs.com/TGnewUI/...` | IBM/Kenexa BrassRing Talent Gateway-style `TGnewUI` (`partnerid=25008`, multiple `siteid`s) | VERIFIED at platform-family level | **No BrassRing adapter** | **ADAPTER_NEEDED** | Build one reusable BrassRing/Talent Gateway adapter if direct structured endpoints are accessible; account for multiple UBS site IDs |
| 29 | BMW Group | `https://jobs.bmwgroup.com/` | SAP SuccessFactors Recruiting Marketing-style career site; job URL and locale structure strongly match RMK, but tenant/API tuple not directly proven here | PROBABLE | **Yes — SuccessFactors RMK** | FAST_PATH candidate | One cheap platform/API fingerprint; if RMK tuple resolves, upgrade to VERIFIED and probe |
| 30 | Mercedes-Benz Group | `https://jobs.mercedes-benz.com/` | Oracle Taleo (`tas-daimler.taleo.net`) is explicitly named by Mercedes-Benz's own legal/cookie pages as part of the recruiting systems | VERIFIED | **No — Oracle Recruiting Cloud adapter is not Taleo** | **ADAPTER_NEEDED** | Determine whether public jobs can be enumerated from Taleo structured endpoints; implement reusable Taleo adapter if useful |
| 31 | Porsche AG | `https://jobs.porsche.com/` | SAP SuccessFactors Recruiting; current Porsche job pages expose apply handoff to `career5.successfactors.eu` with `company=porschecar` | VERIFIED | **Yes — SuccessFactors RMK** | **FAST_PATH** | Derive tenant/company tuple and run full SuccessFactors probe; keep Porsche AG separate from Porsche Holding/VW-group jobs where needed |
| 32 | Airbus | `https://www.airbus.com/en/careers` | Workday, `ag.wd3.myworkdayjobs.com/Airbus` | VERIFIED | **Yes — Workday** | **FAST_PATH** | Derive `wd3 | ag | Airbus` tuple and run structured catalog probe |
| 33 | Lockheed Martin | `https://www.lockheedmartinjobs.com/` | Public career layer is Radancy/TalentBrew; application flow is BrassRing/Talent Gateway | VERIFIED at dual-platform architecture level | **Yes — Radancy**, no BrassRing adapter | **FAST_PATH candidate via Radancy** | First try existing Radancy adapter against public catalog. Only add BrassRing if Radancy cannot provide complete job inventory/descriptions |
| 34 | RTX / Raytheon / Collins Aerospace / Pratt & Whitney | `https://careers.rtx.com/` | Unified first-party RTX custom/hosted career frontend; stable `/global/en/job/<id>/...` URLs, backend family not directly proven in this batch | VERIFIED as unified custom RTX surface; backend UNKNOWN | No proven match | **RESOLVER_NEEDED** | Fingerprint network/backend once for RTX; if solved, reuse across Raytheon, Collins Aerospace and Pratt & Whitney brands |

### Batch-3 result

Of these 10 employers:

- **3 are clear FAST_PATH:** JPMorgan Chase, Porsche, Airbus.
- **2 are strong FAST_PATH candidates requiring only a cheap platform probe:** BMW Group and Lockheed Martin.
- **2 expose known reusable enterprise platforms that are not yet supported:** UBS -> BrassRing/Talent Gateway; Mercedes-Benz -> Oracle Taleo.
- **3 remain genuine custom resolver targets:** Goldman Sachs, Morgan Stanley, RTX.

This batch reveals an important new optimization: the unresolved queue is not only `custom vs supported`. We now have a useful middle class:

```text
KNOWN ENTERPRISE PLATFORM
but adapter missing
```

Those should be solved **once per platform**, then immediately trigger a reclassification of every unresolved employer. A BrassRing adapter, for example, could potentially unlock both UBS and the application side of Lockheed Martin plus other large enterprises.

---

## Evidence / source ledger — Batch 3

### JPMorgan Chase
- Current first-party Candidate Experience jobs resolve under Oracle Fusion/Oracle Recruiting Cloud:
  - `https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/...`
  - `https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1002/...`
- Current listings expose stable numeric `Job Identification` values (for example `210783979`, `210776815`).
- Mapping: **Oracle Recruiting Cloud -> existing adapter**.

### Goldman Sachs
- First-party careers page: `https://www.goldmansachs.com/careers`
- `Open Roles` currently redirects to `https://higher.gs.com/results`.
- `higher.gs.com` is therefore the operational first-party jobs surface, but the underlying structured API/RPC has not yet been frozen.

### Morgan Stanley
- First-party career search: `https://www.morganstanley.com/careers/career-opportunities-search`
- Current page contains quick search, guided search, location/business-area filters and separate experienced/student flows on Morgan Stanley's own domain.
- No supported ATS signature is treated as proven yet.

### UBS
- First-party UBS careers links to `https://jobs.ubs.com/TGnewUI/...`.
- Current public URLs contain `partnerid=25008` and several site IDs (e.g. `5012` experienced professionals; `5131` graduate board).
- `TGnewUI` / partner/site pattern is the Kenexa/IBM BrassRing Talent Gateway family, not Oracle Recruiting Cloud.
- This is therefore a reusable **ADAPTER_NEEDED** platform rather than a one-off UBS custom parser.

### BMW Group
- Public operational jobs surface: `https://jobs.bmwgroup.com/`.
- Current detail URLs use the standard hosted recruiting shape `.../job/<slug>/<numeric-id>-<locale>/` with locale-aware search/profile UI, strongly consistent with SAP SuccessFactors Recruiting Marketing.
- Because this batch did not yet capture the underlying RMK API/company tuple directly, status remains **PROBABLE** rather than VERIFIED.

### Mercedes-Benz Group
- First-party jobs: `https://jobs.mercedes-benz.com/`.
- Mercedes-Benz's own provider/legal and cookie pages explicitly list `tas-daimler.taleo.net` among its job application systems.
- Treat as **Oracle Taleo**, which is technically distinct from the existing Oracle Recruiting Cloud adapter.

### Porsche AG
- First-party jobs: `https://jobs.porsche.com/`.
- A current Porsche Cars North America posting exposes an apply handoff to:
  - `https://career5.successfactors.eu/sfcareer/jobreqcareer?jobId=11205&company=porschecar`
- This directly establishes SAP SuccessFactors Recruiting for at least the relevant Porsche recruiting flow.

### Airbus
- Current first-party operational postings resolve to:
  - `https://ag.wd3.myworkdayjobs.com/Airbus/...`
- Current job pages expose Workday requisition IDs such as `JR10411073`.
- Mapping: **Workday -> existing adapter**.

### Lockheed Martin
- First-party public career site: `https://www.lockheedmartinjobs.com/`.
- Current public search/job architecture is a Radancy/TalentBrew career layer, while application handoff uses BrassRing/Talent Gateway.
- Because the supplied Research Agent already has a Radancy adapter, the cheapest path is **probe Radancy first**, not immediately implement BrassRing specifically for Lockheed.

### RTX
- First-party career platform: `https://careers.rtx.com/`.
- Raytheon, Collins Aerospace and other RTX businesses currently share stable paths such as `/global/en/job/01837740/...`.
- This is strategically valuable: one successful backend resolution may unlock several Tier-S employer brands at once.
- Backend family deliberately remains UNKNOWN until direct request inspection.

---

## Cumulative census after 34 priority employers

Working counts (platform mapping status, **not employer PASS certification**):

```text
clear FAST_PATH / already supported       16
strong FAST_PATH candidates                3
known custom adapter case                  1   (Google, implemented in V24)
known platform but adapter needed           2   (BrassRing, Taleo)
custom / resolver queue                    12
---------------------------------------------
total                                      34
```

Interpretation:

- roughly **half of the first 34 employers are already directly compatible with an existing structured adapter**;
- another meaningful slice can probably be converted with one cheap fingerprint;
- only about a third remain true custom investigation cases at this stage;
- building **platform adapters before company-specific resolvers** should continue shrinking the custom queue.

### Updated execution rule

```text
Employer
  -> deterministic ATS/platform census
      -> existing adapter      -> employer probe
      -> probable existing ATS -> one cheap fingerprint -> employer probe
      -> known unsupported ATS -> build platform adapter once -> reclassify queue
      -> genuinely custom      -> autonomous resolver
```

The next census batch should continue across high-value finance/insurance, automotive and European aerospace/defense employers before we invest in the general resolver.


---

## Tier-S mapping — Batch 4

This batch focuses on banking/payments plus industrial/automotive employers. It also confirms an important architectural pattern: several large employers use a **candidate-experience frontend** (Radancy/Phenom) in front of a separate ATS of record (Workday/Oracle). For Research Agent discovery, prefer whichever supported structured layer can enumerate the public catalog most completely and cheaply; do not assume the application ATS must always be the scan source.

| Priority | Employer | Canonical careers surface | Operational ATS / backend | Confidence | Adapter in supplied ZIP | Path | Next action |
|---:|---|---|---|---|---:|---|---|
| 35 | Capital One | `https://www.capitalonecareers.com/` | Radancy/TalentBrew candidate-experience site; application process uses Workday | VERIFIED at public career-platform level | **Yes — Radancy** | **FAST_PATH** | Probe existing Radancy adapter against the public catalog first; use Workday only if Radancy catalog/detail coverage is incomplete |
| 36 | Deutsche Bank | `https://careers.db.com/` | Workday, public tenant `db.wd3.myworkdayjobs.com`, site `DBWebsite` | VERIFIED | **Yes — Workday** | **FAST_PATH** | Run Workday catalog probe and verify all public requisitions/locations |
| 37 | Mastercard | `https://careers.mastercard.com/` | Phenom candidate-experience site backed by Workday ATS (`mastercard.wd1.myworkdayjobs.com`; CorporateCareers/Campus paths reported) | VERIFIED at platform architecture level | **Yes — Phenom and Workday** | **FAST_PATH** | Prefer the layer yielding the complete public catalog with fewer requests; verify Phenom vs Workday parity once |
| 38 | ING | `https://careers.ing.com/` | Radancy/TalentBrew (`careers-ing-com.talentbrew.com`; Radancy-hosted assets) | VERIFIED at public career-platform level | **Yes — Radancy** | **FAST_PATH** | Run existing Radancy adapter and measure catalog/detail completeness |
| 39 | Allianz Group | `https://careers.allianz.com/global/en/` | SAP SuccessFactors; Allianz first-party accessibility statement explicitly identifies its career site/ATS as SAP SuccessFactors SaaS | VERIFIED | **Yes — SuccessFactors RMK** | **FAST_PATH** | Derive RMK/company parameters and probe global job market |
| 40 | Siemens | `https://jobs.siemens.com/` | Avature; Siemens first-party recruitment/fraud-prevention pages explicitly state applications run through the Avature job portal | VERIFIED | **Yes — Avature** | **FAST_PATH** | Derive Avature tenant/config and probe. Keep Siemens Healthineers separate if its catalog diverges |
| 41 | Bosch Group | `https://www.bosch.com/careers/` / regional Bosch careers surfaces | SmartRecruiters, organization `BoschGroup` | VERIFIED | **Yes — SmartRecruiters** | **FAST_PATH** | Probe SmartRecruiters organization `BoschGroup`; verify whether all regions/legal entities are represented |
| 42 | Rolls-Royce | `https://careers.rolls-royce.com/` | Workday, `rollsroyce.wd3.myworkdayjobs.com`; public sites include `professional` and `Contingent` | VERIFIED | **Yes — Workday** | **FAST_PATH** | Enumerate relevant public Workday site paths, dedup by requisition ID and probe |
| 43 | Volkswagen Group | `https://jobs.volkswagen-group.com/` | SAP SuccessFactors-style Group Job Portal; current UI/signatures and internal Group postings point to SuccessFactors, but external tenant tuple not yet directly captured | PROBABLE | **Yes — SuccessFactors RMK** | **FAST_PATH candidate** | One cheap RMK/tenant fingerprint; if direct tuple resolves, upgrade to VERIFIED and probe group catalog |
| 44 | American Express | `https://www.americanexpress.com/en-us/careers/` | Oracle Recruiting Cloud / Fusion Candidate Experience; current public postings resolve under `*.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/...` and Amex recruitment-tech roles explicitly describe ORC rollout | VERIFIED | **Yes — Oracle Recruiting Cloud** | **FAST_PATH** | Resolve current public ORC host/site IDs (e.g. `CX_1`) and run Oracle catalog probe |

### Batch-4 result

Of these 10 employers:

- **9 are clear FAST_PATH candidates using adapters already present in the supplied ZIP:** Capital One, Deutsche Bank, Mastercard, ING, Allianz, Siemens, Bosch, Rolls-Royce and American Express.
- **1 is a very strong FAST_PATH candidate needing only a cheap tenant fingerprint:** Volkswagen Group -> SuccessFactors.
- **0 require a new custom resolver in this batch.**

This is the strongest batch so far and materially changes the expected cost of onboarding the CORE universe. The dominant pattern is now:

```text
branded career frontend
    -> known hosted platform
    -> existing adapter
    -> controlled employer probe
```

rather than:

```text
custom portal
    -> browser investigation
    -> new code
```

The distinction between **career-experience layer** and **ATS of record** also matters. For example:

```text
Capital One: Radancy/TalentBrew -> Workday apply
Mastercard:  Phenom            -> Workday ATS
```

Research Agent should scan the cheapest structured public layer that can prove a complete catalog; it does not need to follow the candidate all the way into the application system if the frontend API already exposes the complete vacancy dataset.

---

## Evidence / source ledger — Batch 4

### Capital One
- First-party careers/search: https://www.capitalonecareers.com/search-jobs
- Capital One FAQ explicitly states the full application is completed in Workday: https://www.capitalonecareers.com/faq/
- Public career hostname currently resolves via TalentBrew/Radancy infrastructure (`www-capitalonecareers-com.talentbrew.com`); Radancy-hosted Capital One assets are also observable.
- Operational decision: test the existing Radancy adapter first because it is the public catalog layer; Workday is the downstream application system.

### Deutsche Bank
- First-party careers search: https://careers.db.com/professionals/search-roles/
- Current public postings are directly available at `https://db.wd3.myworkdayjobs.com/.../DBWebsite/...` with stable requisition IDs such as `R0420105`.

### Mastercard
- First-party careers: https://careers.mastercard.com/
- Phenom publicly documents Mastercard as a Phenom career-site customer and explicitly lists **ATS: Workday**:
  - https://www.phenom.com/resource/transforming-mastercard-talent-acquisition
- Current career links use Phenom-style URLs such as `/us/en/job/MASRUSR...`.
- Current evidence identifies the downstream Workday tenant as `mastercard.wd1.myworkdayjobs.com`; verify tenant/site paths during probe rather than hard-coding from third-party evidence.

### ING
- First-party careers/search: https://careers.ing.com/en/search_jobs
- Current DNS/hosting evidence maps `careers.ing.com` to `careers-ing-com.talentbrew.com`.
- Current ING content assets are hosted under `cdn.radancy.eu/company/2618/...`.
- This is sufficient to classify the public catalog layer as Radancy/TalentBrew.

### Allianz Group
- First-party careers: https://careers.allianz.com/global/en/
- Allianz first-party accessibility statement explicitly says: **“Allianz's career website and online application system is based on SAP SuccessFactors technology (SaaS)”**:
  - https://careers.allianz.com/global/en/accessibility
- Public jobs use stable first-party URLs such as `/job/<location>/<title>/<id>/`, consistent with SuccessFactors RMK career sites.

### Siemens
- First-party jobs: https://jobs.siemens.com/
- Siemens first-party recruitment/fraud-prevention pages explicitly state that selection processes run through the **Avature** jobs portal at `jobs.siemens.com`.
- Current role URLs follow Avature-style paths such as `https://jobs.siemens.com/careers/job/<id>`.

### Bosch Group
- Current Bosch organization board: https://careers.smartrecruiters.com/BoschGroup
- Current live postings: `https://jobs.smartrecruiters.com/BoschGroup/<id>-<slug>`.
- SmartRecruiters Bosch pages explicitly name SmartRecruiters as the partner/provider.

### Rolls-Royce
- First-party careers: https://careers.rolls-royce.com/en
- Current public roles resolve directly to Workday, e.g.:
  - `https://rollsroyce.wd3.myworkdayjobs.com/en-US/professional/...`
  - `https://rollsroyce.wd3.myworkdayjobs.com/en-US/Contingent/...`
- Stable requisition IDs use the `JR...` form.

### Volkswagen Group
- First-party Group Job Portal: https://jobs.volkswagen-group.com/
- Portal structure strongly matches SAP SuccessFactors Recruiting Marketing (`View Profile`, keyword/location search, standard RMK layout).
- Current Volkswagen Group internal recruiting posts explicitly refer employees to the Group Job Portal / SuccessFactors.
- Direct external RMK tenant/company tuple still needs one cheap fingerprint, therefore confidence remains PROBABLE rather than VERIFIED.

### American Express
- First-party careers: https://www.americanexpress.com/en-us/careers/
- Current 2026 public American Express jobs are available under Oracle Fusion Candidate Experience hosts such as:
  - `https://egug.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/<id>`
- American Express recruitment-system roles in 2026 explicitly describe the enterprise rollout and ongoing use of **Oracle Recruiting Cloud (ORC)**.
- Treat host/site IDs as configuration discovered at probe time rather than assuming one global site forever.

---

## Cumulative census after Batch 4

Current working counts across **44 mapped employers including Stripe baseline**:

```text
clear FAST_PATH / existing adapter        ≈ 25
strong FAST_PATH candidates               ≈ 4
known custom already solved               = 1   (Google V24)
known platform but adapter missing         = 2   (BrassRing, Taleo cases seen so far)
custom / resolver-needed queue            ≈ 12
```

The exact counts remain intentionally provisional until every `PROBABLE` mapping is upgraded/downgraded by a direct probe, but the architectural conclusion is already robust:

> **Most high-value employers should not be sent to an autonomous resolver.**

A cheap deterministic ATS census + existing-adapter probe is now the default path. The future resolver should only receive the residual custom/unknown queue.

---

## Tier-S mapping — Batch 5

This batch extends the census into cloud/data infrastructure, developer platforms, semiconductors and large enterprise software. It is deliberately conservative: where the current career frontend is clearly first-party but the operational backend family is not directly proven, the employer stays in `RESOLVER_NEEDED` rather than being force-mapped to a familiar ATS.

| Priority | Employer | Canonical careers surface | Operational ATS / backend | Confidence | Adapter in supplied ZIP | Path | Next action |
|---:|---|---|---|---|---:|---|---|
| 45 | Snowflake | `https://careers.snowflake.com/` | First-party Snowflake careers frontend; structured backend not directly frozen in this batch | UNKNOWN at backend level | No proven match | **RESOLVER_NEEDED** | Inspect search/detail network calls; only then decide whether an existing adapter applies |
| 46 | MongoDB | `https://www.mongodb.com/company/careers/see-jobs` | Greenhouse, board token `mongodb` | VERIFIED | **Yes — Greenhouse** | **FAST_PATH** | Probe Greenhouse board `mongodb`; compare count against MongoDB first-party careers surface |
| 47 | GitLab | `https://about.gitlab.com/jobs/` / GitLab jobs page | Greenhouse, board token `gitlab`; separate `gitlabcrm` prospect/expression-of-interest board also exists | VERIFIED | **Yes — Greenhouse** | **FAST_PATH** | Scan `gitlab` as active-vacancy source; do not merge `gitlabcrm` expressions of interest into live-job catalog |
| 48 | Elastic | `https://jobs.elastic.co/` | Greenhouse behind a vanity/custom Elastic domain; public board/API token `elastic` | VERIFIED | **Yes — Greenhouse** | **FAST_PATH** | Use Greenhouse API token `elastic`; vanity domain should remain canonical display surface where useful |
| 49 | ServiceNow | `https://careers.servicenow.com/jobs` | SmartRecruiters organization `ServiceNow` is publicly active; first-party ServiceNow frontend mirrors/consumes the same openings | VERIFIED at ATS-family level | **Yes — SmartRecruiters** | **FAST_PATH** | Probe SmartRecruiters `ServiceNow`; compare current count with first-party jobs page |
| 50 | Salesforce | `https://careers.salesforce.com/en/jobs/` | Salesforce first-party custom jobs frontend currently exposes complete pagination/result data; downstream ATS/backend not proven here | UNKNOWN at backend level | No proven match | **RESOLVER_NEEDED** | Inspect first-party search API/network. Prefer structured Salesforce endpoint over guessing Workday from internal HR usage |
| 51 | Adobe | `https://careers.adobe.com/` | Adobe first-party custom/hosted career frontend; operational ATS family not directly proven in this batch | UNKNOWN | No proven match | **RESOLVER_NEEDED** | Inspect current search/detail calls and fingerprint platform before adapter work |
| 52 | IBM | `https://careers.ibm.com/` | IBM Talent Acquisition Suite / Kenexa-BrassRing lineage; current IBM candidate flow retains BrassRing/Talent Gateway identifiers (`partnerid=26059`, `siteid=5016`) | VERIFIED at platform-family level | **No BrassRing adapter** | **ADAPTER_NEEDED** | Treat IBM + UBS as evidence that a reusable BrassRing adapter has real ROI; investigate current public enumeration endpoints once |
| 53 | Intel | `https://jobs.intel.com/` | Workday, tenant/site publicly observed as `intel.wd1.myworkdayjobs.com/External` | VERIFIED | **Yes — Workday** | **FAST_PATH** | Derive Workday tuple and probe catalog; preserve Intel requisition IDs (`JR...`) |
| 54 | AMD | `https://careers.amd.com/careers-home/jobs` | First-party hosted jobs frontend with stable numeric job IDs and full descriptions; underlying platform family not directly proven here | VERIFIED as structured first-party surface; backend UNKNOWN | No proven match | **RESOLVER_NEEDED** | Inspect network/API behind `/careers-home/jobs`; likely cheap because listing/detail data are already server-visible |
| 55 | Qualcomm | `https://careers.qualcomm.com/` | Workday strongly indicated by public Qualcomm application/job links, but current tenant/site tuple was not captured from first-party evidence in this batch | PROBABLE | **Yes — Workday** | **FAST_PATH candidate** | One cheap Workday-domain/tenant confirmation, then probe |
| 56 | Oracle | `https://www.oracle.com/careers/` | Oracle Recruiting Cloud / Fusion Candidate Experience is the expected first-party recruiting stack, but public site/host tuple should be captured directly before freezing | PROBABLE | **Yes — Oracle Recruiting Cloud** | **FAST_PATH candidate** | Follow current `Search jobs at Oracle` handoff, capture ORC host/site IDs, then probe |
| 57 | SAP | `https://jobs.sap.com/` | SAP SuccessFactors Recruiting Marketing (RMK); SAP support documentation itself uses `jobs.sap.com` as the production RMK example | VERIFIED | **Yes — SuccessFactors RMK** | **FAST_PATH** | Derive SAP RMK feed/company parameters and probe; useful reference fixture for the SuccessFactors adapter |
| 58 | Booking.com | `https://careers.booking.com/` / `https://jobs.booking.com/` | SmartRecruiters organization `Bookingcom1` is publicly active and exposes Booking.com roles | VERIFIED at ATS-family level | **Yes — SmartRecruiters** | **FAST_PATH** | Probe `Bookingcom1`; compare with first-party jobs catalog and identify whether additional regional org IDs exist |
| 59 | Spotify | `https://www.lifeatspotify.com/jobs` | Lever, organization `spotify`; Spotify's own candidate FAQ explicitly says legitimate full-time job links can begin with `https://jobs.lever.co/spotify` | VERIFIED first-party | **Yes — Lever** | **FAST_PATH** | Run Lever probe for `spotify`; use Life at Spotify as canonical careers surface |

### Batch-5 result

Of these 15 employers:

- **7 are clear FAST_PATH:** MongoDB, GitLab, Elastic, ServiceNow, Intel, SAP, Booking.com, Spotify. (Eight rows are listed here because Spotify is included; count = 8.)
- **2 are strong FAST_PATH candidates needing one cheap fingerprint:** Qualcomm and Oracle.
- **1 is a known reusable unsupported platform:** IBM -> BrassRing/Talent Gateway.
- **4 remain genuine resolver/backend-discovery work:** Snowflake, Salesforce, Adobe, AMD.

Corrected arithmetic for this batch:

```text
clear FAST_PATH                  8
strong FAST_PATH candidates      2
known platform / adapter needed  1
custom / resolver                4
----------------------------------
total                            15
```

The most important new result is **BrassRing recurrence**. UBS was already mapped to BrassRing/Talent Gateway in Batch 3; IBM now gives us a second high-value employer on the same family. That is enough to move BrassRing from “maybe later” toward a real reusable-adapter candidate. By contrast, Taleo still has only the Mercedes-Benz case in this ledger, so BrassRing currently has higher adapter ROI.

Another useful rule emerges from GitLab: separate **live vacancy boards** from **talent-community / prospect boards** even when both use the same ATS. `gitlab` is the active-job board; `gitlabcrm` contains expressions of interest and should not contaminate the vacancy catalog.

---

## Evidence / source ledger — Batch 5

### Snowflake
- First-party careers: https://careers.snowflake.com/
- Current page exposes the careers experience but this batch did not capture a supported ATS domain or structured endpoint strongly enough to freeze the backend.

### MongoDB
- First-party careers: https://www.mongodb.com/company/careers/see-jobs
- Greenhouse board/application identity observed as `mongodb`:
  - https://job-boards.greenhouse.io/embed/job_app?for=mongodb
- Treat Greenhouse board token `mongodb` as operational source candidate for probe.

### GitLab
- GitLab candidate documentation explicitly instructs team members/candidates around Greenhouse.
- Current live public board:
  - https://job-boards.greenhouse.io/gitlab
- Separate prospect/expression-of-interest board exists:
  - https://job-boards.greenhouse.io/gitlabcrm
- Only the live vacancy board belongs in the normal active-job catalog.

### Elastic
- First-party vanity jobs domain: https://jobs.elastic.co/
- Greenhouse board/API identity is `elastic`.
- Public Greenhouse API pattern has been observed at:
  - `https://boards-api.greenhouse.io/v1/boards/elastic/jobs`
- This is a useful test case for detecting Greenhouse behind a custom domain rather than relying on hostname alone.

### ServiceNow
- First-party jobs: https://careers.servicenow.com/jobs
- Public SmartRecruiters organization:
  - https://careers.smartrecruiters.com/ServiceNow
- Current SmartRecruiters page exposes the active ServiceNow opening inventory, making this an existing-adapter fast path pending employer-level parity probe.

### Salesforce
- First-party current jobs: https://careers.salesforce.com/en/jobs/
- Current page exposes paginated result counts directly (roughly 1.5k roles at the time of this census).
- No ATS is frozen from indirect evidence; inspect the frontend requests before deciding whether this is an existing-platform case.

### Adobe
- First-party careers: https://careers.adobe.com/
- Current hosted frontend is clearly functional but no current supported ATS signature was captured strongly enough in this pass.

### IBM
- First-party careers: https://careers.ibm.com/
- IBM recruiting flows have used the Kenexa/BrassRing Talent Gateway family with identifiers such as:
  - `partnerid=26059`
  - `siteid=5016`
- Candidate communications also use `@trm.brassring.com` infrastructure.
- Strategic implication: investigate a **reusable BrassRing adapter** for both IBM and UBS rather than company-specific code.

### Intel
- Intel-authored/current recruiting material links directly to:
  - `https://intel.wd1.myworkdayjobs.com/External/...`
- Current requisitions use IDs such as `JR0280731`.
- Mapping: Workday -> existing adapter.

### AMD
- First-party jobs catalog: https://careers.amd.com/careers-home/jobs
- Current detail URLs use stable numeric identities such as:
  - `https://careers.amd.com/careers-home/jobs/79275`
  - `https://careers.amd.com/careers-home/jobs/87746`
- Full descriptions are server-visible. This looks likely to be a cheap custom-backend resolution even though platform family remains unproven.

### Qualcomm
- Public Qualcomm recruiting links have repeatedly used Workday/MyWorkdayJobs.
- Current mapping stays PROBABLE until the present external tenant/site is captured directly; do not freeze from stale URL evidence alone.

### Oracle
- First-party careers: https://www.oracle.com/careers/
- Oracle's own recruiting stack is expected to use Oracle Fusion / Recruiting Cloud Candidate Experience, but the current public Candidate Experience host/site IDs must be observed before VERIFIED status.

### SAP
- First-party jobs: https://jobs.sap.com/
- SAP's own SuccessFactors support documentation explicitly uses `jobs.sap.com` as an example of a production **Recruiting Marketing (RMK)** career-site URL.
- This is strong first-party platform evidence and should become a reference fixture for the existing SuccessFactors adapter.

### Booking.com
- First-party careers: https://careers.booking.com/
- Public SmartRecruiters organization:
  - https://careers.smartrecruiters.com/Bookingcom1
- Current first-party site exposes role categories including `Security & Infrastructure`; use SmartRecruiters as the initial operational-source candidate and verify parity.

### Spotify
- First-party careers: https://www.lifeatspotify.com/start-your-journey
- Spotify's own candidate guidance states that legitimate Spotify full-time job links can begin with:
  - `https://lifeatspotify.com/jobs`
  - `https://jobs.lever.co/spotify`
- This is direct first-party evidence for Lever organization `spotify`.

---

## Cumulative census after Batch 5

Current working census across **59 mapped employers including Stripe baseline**:

```text
clear FAST_PATH / existing adapter        ≈ 33
strong FAST_PATH candidates               ≈ 6
known custom already solved               = 1   (Google V24)
known platform but adapter missing         = 3   platform-employer cases, notably BrassRing recurrence + Taleo
custom / resolver-needed queue            ≈ 16
```

These counts remain provisional because previous batches intentionally contain `PROBABLE` rows, but the high-level result is now stronger:

> **Roughly two thirds of the mapped employers are already supported or one cheap fingerprint away from an existing adapter.**

The next engineering investment should therefore *not* be a universal portal resolver yet. The current ROI order is:

1. finish the ATS census toward ~80 employers;
2. validate the existing-adapter fast paths in ATS-family batches;
3. investigate **BrassRing once** because it now recurs across multiple high-value employers;
4. re-run classification after each new platform adapter;
5. send only the residual custom queue to an autonomous resolver.


---

## Tier-S mapping — Batch 6

This batch pushes the census from 59 to 75 employers, with a deliberate mix of cybersecurity vendors and finance/fintech targets. A key rule is reinforced here: **historical ATS evidence is not enough**. If a formerly known board is dead or now redirects to a first-party surface, the employer stays `PROBABLE` / `RESOLVER_NEEDED` until the current operational source is proven.

| Priority | Employer | Canonical careers surface | Operational ATS / backend | Confidence | Adapter in supplied ZIP | Path | Next action |
|---:|---|---|---|---|---:|---|---|
| 60 | Check Point Software | `https://www.checkpoint.com/careers/` | SmartRecruiters organization `CheckPointSoftwareTechnologies2` | VERIFIED at current ATS-family level | **Yes — SmartRecruiters** | **FAST_PATH** | Probe SmartRecruiters org `CheckPointSoftwareTechnologies2`; compare catalog count against first-party careers search |
| 61 | CyberArk | `https://www.cyberark.com/careers/` | SmartRecruiters organization `Cyberark1` | VERIFIED at current ATS-family level | **Yes — SmartRecruiters** | **FAST_PATH** | Probe `Cyberark1`; keep corporate ownership change separate from vacancy identity |
| 62 | Tenable | `https://www.tenable.com/careers` | Greenhouse, board token `tenableinc` | VERIFIED | **Yes — Greenhouse** | **FAST_PATH** | Probe Greenhouse board `tenableinc`; compare with Tenable first-party search |
| 63 | Fastly | `https://www.fastly.com/about/careers/current-openings` | Greenhouse, board token `fastly`; board redirects/embeds into first-party experience but Greenhouse job-app endpoints remain observable | VERIFIED at platform-family level | **Yes — Greenhouse** | **FAST_PATH** | Probe Greenhouse API token `fastly`; verify current first-party opening count and descriptions |
| 64 | Proofpoint | `https://www.proofpoint.com/us/company/careers` | Workday, `proofpoint.wd5.myworkdayjobs.com/ProofpointCareers` | VERIFIED | **Yes — Workday** | **FAST_PATH** | Derive `wd5 | proofpoint | ProofpointCareers` tuple and run Workday probe |
| 65 | Rubrik | `https://www.rubrik.com/company/careers` | Rich first-party careers catalog; legacy/vanity Greenhouse URL currently redirects back to Rubrik first-party careers, so operational structured backend is not frozen | VERIFIED first-party surface; backend UNKNOWN | No proven current adapter match | **RESOLVER_NEEDED** | Inspect current Rubrik search/filter requests and identify the datasource powering first-party category counts/jobs |
| 66 | Netskope | `https://www.netskope.com/company/careers/open-positions` | First-party open-positions surface; `job-boards.greenhouse.io/netskope` currently redirects to Netskope, suggesting Greenhouse lineage/vanity but not yet proving the current API contract | PROBABLE Greenhouse lineage, current backend TBD | Maybe — Greenhouse | FAST_PATH candidate / fingerprint first | Test Greenhouse Boards API token `netskope`; if live and catalog parity holds, upgrade to FAST_PATH, otherwise inspect first-party network |
| 67 | Snyk | `https://snyk.io/careers/all-jobs/` | Current first-party JavaScript jobs app; historical Greenhouse board existed, but `job-boards.greenhouse.io/snyk` now returns 404 | VERIFIED current custom surface; historical Greenhouse no longer sufficient | No proven current match | **RESOLVER_NEEDED** | Inspect current Snyk jobs app network/API; do **not** reuse stale Greenhouse mapping without live evidence |
| 68 | Akamai | `https://www.akamai.com/careers` | First-party Akamai careers/search flow; current structured ATS/backend not established in this batch | UNKNOWN at backend level | No proven match | **RESOLVER_NEEDED** | Follow current search handoff and fingerprint API/ATS before implementation |
| 69 | Adyen | `https://careers.adyen.com/` | Greenhouse, board token `adyen`; current first-party career site mirrors hundreds of vacancies | VERIFIED | **Yes — Greenhouse** | **FAST_PATH** | Probe Greenhouse board `adyen`; compare active count and canonical URLs against Adyen first-party vacancies |
| 70 | BlackRock | `https://careers.blackrock.com/en/search-jobs` | Rich first-party BlackRock job-search frontend with stable searchable catalog; underlying ATS/backend not frozen in this batch | VERIFIED first-party surface; backend UNKNOWN | No proven match | **RESOLVER_NEEDED** | Inspect search pagination/network; prefer first-party structured endpoint if exposed |
| 71 | Citi | `https://jobs.citi.com/` | First-party Citi jobs frontend; Eightfold is explicitly used for candidate matching, but that does **not** prove Eightfold is the authoritative vacancy catalog backend | VERIFIED first-party surface; catalog backend UNKNOWN | No Eightfold adapter | **RESOLVER_NEEDED** | Inspect Citi search API separately from Eightfold “Match Me”; do not conflate recommendation layer with source catalog |
| 72 | Bank of America | `https://careers.bankofamerica.com/en-us/job-search` | First-party Bank of America search UI; operational ATS/backend not frozen | VERIFIED first-party surface; backend UNKNOWN | No proven match | **RESOLVER_NEEDED** | Inspect search/filter requests and stable requisition identity; avoid generic HTML if structured endpoint exists |
| 73 | Revolut | `https://www.revolut.com/careers/` | First-party Revolut careers catalog currently exposes hundreds of openings; backend/platform family not proven in this batch | VERIFIED first-party surface; backend UNKNOWN | No proven match | **RESOLVER_NEEDED** | Inspect current vacancies API; likely a high-value custom resolver target because the first-party catalog is already highly structured |
| 74 | Wise | `https://wise.jobs/` | First-party Wise jobs/careers experience; current operational ATS family not proven | UNKNOWN at backend level | No proven match | **RESOLVER_NEEDED** | Fingerprint job-search API/redirects before mapping; ignore unrelated Greenhouse organization named “Wise” |
| 75 | Rapid7 | `https://careers.rapid7.com/` | Current first-party careers surface; no live supported ATS signature was proven in this batch | UNKNOWN | No proven match | **RESOLVER_NEEDED** | Inspect current search/detail network contract; do not assume historical ATS |

### Batch-6 result

This batch adds:

```text
clear FAST_PATH                = 5
FAST_PATH candidate            = 1
custom / resolver needed       = 10
```

The cumulative 75-employer census now has two important characteristics:

1. **Known supported ATS still dominate the easy half** of the universe: Greenhouse, Workday and SmartRecruiters continue to generate immediate fast paths.
2. **The remaining hard queue is increasingly made of genuinely first-party/custom portals**, not merely missed ATS fingerprints. This is exactly the subset where an autonomous resolver will provide real value.

The Snyk/Rubrik/Netskope cases also establish an important maintenance rule:

```text
historical ATS mapping
!=
current operational source
```

A board that redirects, disappears, or no longer exposes the catalog must be re-fingerprinted rather than trusted indefinitely.

---

## Evidence / source ledger — Batch 6

### Check Point Software
- First-party careers: https://www.checkpoint.com/careers/
- Current SmartRecruiters postings: https://jobs.smartrecruiters.com/CheckPointSoftwareTechnologies2/
- Example current posting: `.../CheckPointSoftwareTechnologies2/744000142902987-...`

### CyberArk
- First-party careers: https://www.cyberark.com/careers/
- Current SmartRecruiters organization: https://jobs.smartrecruiters.com/Cyberark1/
- Current 2026 SmartRecruiters job pages identify CyberArk as a Palo Alto Networks company; vacancy identity should remain CyberArk where the posting is under that brand.

### Tenable
- First-party careers: https://www.tenable.com/careers
- Live Greenhouse board: https://job-boards.greenhouse.io/tenableinc
- Board currently exposes dozens of live roles and departments.

### Fastly
- First-party openings: https://www.fastly.com/about/careers/current-openings
- Greenhouse lineage/current job-app evidence: `https://job-boards.greenhouse.io/embed/job_app?for=fastly&token=...`
- The first-party page currently exposes departments including Information Security.

### Proofpoint
- Current Workday site: https://proofpoint.wd5.myworkdayjobs.com/ProofpointCareers
- Example live/current posting uses requisition IDs such as `R14571`.

### Rubrik
- First-party careers: https://www.rubrik.com/company/careers
- Current page exposes category-level opening counts and live jobs directly.
- `https://job-boards.greenhouse.io/rubrik` currently redirects to the first-party Rubrik careers page, so this batch does not treat Greenhouse as proven operational catalog API.

### Netskope
- First-party careers: https://www.netskope.com/company/careers/open-positions
- `https://job-boards.greenhouse.io/netskope` currently redirects to the first-party open-positions surface.
- Greenhouse should therefore be tested as a candidate source, not assumed.

### Snyk
- First-party careers: https://snyk.io/careers/all-jobs/
- Historical Greenhouse job pages exist in search indexes, but the current board URL `https://job-boards.greenhouse.io/snyk` returns 404.
- Current mapping is intentionally downgraded to custom/unknown until the live jobs app datasource is identified.

### Akamai
- First-party careers: https://www.akamai.com/careers
- Current page exposes “Search opportunities,” but this batch did not establish a supported ATS family from direct evidence.

### Adyen
- First-party careers: https://careers.adyen.com/
- Live Greenhouse board: https://job-boards.greenhouse.io/adyen
- Current first-party and Greenhouse surfaces both expose large active catalogs.

### BlackRock
- First-party search: https://careers.blackrock.com/en/search-jobs
- Current search surface exposes hundreds of jobs, stable titles/locations/teams and pagination.

### Citi
- First-party careers/search: https://jobs.citi.com/
- Citi explicitly exposes an Eightfold-powered “Match Me” feature; this is treated as recommendation/matching evidence only, not proof that Eightfold is the canonical jobs datasource.

### Bank of America
- First-party job search: https://careers.bankofamerica.com/en-us/job-search
- Current UI exposes requisition search, locations, divisions and career-area filters directly.

### Revolut
- First-party careers: https://www.revolut.com/careers/
- Current careers page exposes hundreds of openings and team/location filters directly.

### Wise
- First-party careers: https://wise.jobs/
- Important disambiguation: `job-boards.greenhouse.io/wise` belongs to an unrelated Wise/Horace Mann business, **not Wise plc / Wise Payments**.

### Rapid7
- First-party careers: https://careers.rapid7.com/
- No current supported ATS signature was promoted without direct live evidence.

---

## Decision checkpoint after 75 employers

Do not build new adapters simply because a platform appears once. Current priorities should be:

1. **Exploit the existing FAST_PATH queue first** with automated family-level probes.
2. **BrassRing remains the strongest new-adapter candidate** because IBM + UBS (and parts of other enterprise flows) already demonstrate reuse value.
3. **Oracle Taleo is second-tier adapter work** until more CORE employers are confirmed on it.
4. **The custom resolver is now justified**, but only for the shrinking first-party/custom queue; it should not sit in front of Greenhouse/Workday/SmartRecruiters/etc.
5. Add a future `last_verified_at` / re-fingerprint policy because ATS mappings can change over time (Snyk is the concrete example).

---

# Verification methodology v2 — authoritative from 2026-09-02 onward

The earlier batches mixed several evidence qualities under the single label `VERIFIED`. That is too weak for automatic routing. From this point onward, **this section supersedes the legacy confidence labels above**.

## Evidence classes

- **FIRST_PARTY_VERIFIED** — current first-party careers/job surface itself proves the operational platform/backend, or the company explicitly names it.
- **TECHNICALLY_VERIFIED** — a current live ATS/platform endpoint clearly serves the employer's vacancies and has stable current job records, even if the first-party landing page does not explicitly name the vendor.
- **PROBABLE** — current evidence strongly suggests a platform, but we have not yet captured a decisive first-party/technical proof.
- **UNVERIFIED** — only historical, aggregator, directory, stale, or inferential evidence exists. This status may not trigger `FAST_PATH` automatically.

## Routing rule

A future automated census/resolver must obey:

```text
FIRST_PARTY_VERIFIED / TECHNICALLY_VERIFIED
    + adapter exists
        -> READY_TO_PROBE

PROBABLE / UNVERIFIED
        -> fingerprint first
        -> never auto-route from historical ATS knowledge alone
```

A mapping may be operationally downgraded at any time if the live board disappears, redirects to a different platform, or first-party catalog parity fails.

## Audit correction

All legacy rows above should be interpreted conservatively until re-audited under v2. In particular, prior references to external ATS directories, vendor case studies, LinkedIn posts, historical postings, or search-engine snippets are **supporting evidence only**, not sufficient by themselves for automated platform selection.

The following mappings have been re-checked in this audit against current live operational/first-party surfaces and are safe to treat as audited now:

| Employer | Current evidence | Audit v2 status | Operational conclusion |
|---|---|---|---|
| Google | current first-party Google Careers + project-captured structured RPC | FIRST_PARTY_VERIFIED | Custom Google Careers RPC; V24 adapter path |
| NVIDIA | live `nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite` operational surface | TECHNICALLY_VERIFIED | Workday |
| CrowdStrike | live `crowdstrike.wd5.myworkdayjobs.com/crowdstrikecareers` operational surface | TECHNICALLY_VERIFIED | Workday |
| Palantir | live `jobs.lever.co/palantir` board with current openings | TECHNICALLY_VERIFIED | Lever |
| OpenAI | live `jobs.ashbyhq.com/openai` job records | TECHNICALLY_VERIFIED | Ashby |
| Anthropic | live `job-boards.greenhouse.io/anthropic` with current openings | TECHNICALLY_VERIFIED | Greenhouse |
| Tenable | live `job-boards.greenhouse.io/tenableinc` with current openings | TECHNICALLY_VERIFIED | Greenhouse |
| GitLab | live `job-boards.greenhouse.io/gitlab` current opening catalog | TECHNICALLY_VERIFIED | Greenhouse |
| Booking.com | live `careers.smartrecruiters.com/Bookingcom1` catalog | TECHNICALLY_VERIFIED | SmartRecruiters |
| Adyen | live `job-boards.greenhouse.io/adyen` current opening catalog | TECHNICALLY_VERIFIED | Greenhouse |

Everything else remains useful as a hypothesis/working mapping but **must not be treated as automation-grade VERIFIED solely because an older batch says VERIFIED**. We will promote rows incrementally as we touch them.

---

## Tier-S mapping — Batch 7 (verification-v2 only)

This batch deliberately uses the stricter evidence model. If the platform cannot be proven from a current operational surface, it stays resolver/fingerprint work even when an ATS is historically associated with the employer.

| Priority | Employer | Canonical/current careers surface | Operational ATS / backend | Audit v2 confidence | Adapter in supplied ZIP | Path | Next action |
|---:|---|---|---|---|---:|---|---|
| 76 | BAE Systems | `https://careers.baesystems.com/` + `https://jobs.baesystems.com/global/en/` + `https://jobsearch.baesystems.com/` | At least two current public career surfaces. `jobs.baesystems.com` shows Phenom-hosted assets/feed signatures; global `jobsearch.baesystems.com` is a separate live catalog surface | TECHNICALLY_VERIFIED as multi-surface; full authoritative-source parity not yet proven | **Yes — Phenom**, possibly another supported family for global | **PARTIAL_FAST_PATH / FINGERPRINT** | Probe Phenom surface, then compare against global `jobsearch.baesystems.com`; do not assume one surface covers all geographies |
| 77 | Thales | `https://careers.thalesgroup.com/global/en/search-results` | Current first-party URLs use Phenom-style stable job paths and current distribution links include `utm_medium=phenom-feeds` | TECHNICALLY_VERIFIED platform signature | **Yes — Phenom** | **FAST_PATH candidate** | Run Phenom adapter probe and compare count (~3.5k current first-party results) before promotion to PASS |
| 78 | Ericsson | `https://jobs.ericsson.com/` | Current first-party jobs UI uses `careers?domain=ericsson.com&pid=...`; an Ericsson-branded current candidate event is explicitly hosted on `ericsson.eightfold.ai` and links back to `jobs.ericsson.com` | TECHNICALLY_VERIFIED Eightfold ecosystem; authoritative catalog endpoint still to fingerprint | **No Eightfold adapter** | **ADAPTER_NEEDED / RESOLVER** | Inspect current search/detail API once; if Eightfold is the catalog source, build reusable Eightfold adapter |
| 79 | Saab | `https://www.saab.com/career/job-opportunities` | Rich first-party catalog, currently hundreds of live openings with title/location/closing date; ATS family not exposed by current page evidence gathered here | FIRST_PARTY_VERIFIED surface; backend UNVERIFIED | No proven match | **RESOLVER_NEEDED** | Inspect first-party search/detail network; catalog looks structured enough for a cheap custom endpoint discovery |
| 80 | Northrop Grumman | `https://www.northropgrumman.com/jobs-search` | Current first-party search and job discovery are live, but no automation-grade ATS/backend proof captured in this audit | FIRST_PARTY_VERIFIED surface; backend UNVERIFIED | No proven match | **RESOLVER_NEEDED** | Inspect current search network/API; do not infer Workday from historical HR tooling |
| 81 | Shell | `https://jobs.shell.com/search-jobs` | Current first-party searchable catalog is directly visible and includes structured categories/locations; backend vendor not proven here | FIRST_PARTY_VERIFIED surface; backend UNVERIFIED | No proven match yet | **RESOLVER_NEEDED** | Fingerprint first-party search endpoint; likely cheaper than generic HTML because catalog data are already structured |
| 82 | bp | `https://careers.bp.com/` / `https://careers.bp.com/listing` | Current first-party careers/listing experience is live; backend vendor not proven in this audit | FIRST_PARTY_VERIFIED surface; backend UNVERIFIED | No proven match yet | **RESOLVER_NEEDED** | Inspect listing/search API and stable job identity |
| 83 | Coinbase | `https://www.coinbase.com/careers/positions` | Current first-party positions page directly exposes categorized openings and filters. No live Greenhouse/Ashby/etc. mapping is assumed without current proof | FIRST_PARTY_VERIFIED surface; backend UNVERIFIED | No proven match yet | **RESOLVER_NEEDED** | Inspect first-party positions API; likely straightforward because full catalog is already client-visible |
| 84 | Wiz | `https://www.wiz.io/careers` | Current first-party careers page is live; it explicitly says official jobs are posted on Wiz careers and LinkedIn, but does not expose an ATS vendor in the evidence gathered here | FIRST_PARTY_VERIFIED surface; backend UNVERIFIED | No proven match yet | **RESOLVER_NEEDED** | Follow `See open positions`, inspect network/redirect, and only then map ATS |
| 85 | Schneider Electric | `https://www.se.com/it/it/about-us/careers/overview/` and global equivalents | Current first-party careers surface verified; operational catalog backend not captured directly in this audit | FIRST_PARTY_VERIFIED surface; backend UNVERIFIED | No proven match yet | **RESOLVER_NEEDED / cheap fingerprint** | Follow current job-search handoff and capture operational source before using any historical Workday mapping |

### Batch-7 evidence notes

- **BAE Systems:** current `jobs.baesystems.com` pages load Phenom-hosted assets; current job URLs are distributed with `utm_medium=phenom-feeds`. The separate `jobsearch.baesystems.com` catalog is also live, so this is explicitly a multi-surface problem, not a blind Phenom fast path.
- **Thales:** current first-party search exposes thousands of jobs with stable `.../global/en/job/<id>/...` paths; current job distribution links contain `utm_medium=phenom-feeds`.
- **Ericsson:** current `jobs.ericsson.com` has live job search with `domain=ericsson.com` and stable numeric `pid`; Ericsson-branded Eightfold candidate surfaces exist and link to the same first-party careers system. Treat Eightfold as the ecosystem candidate, but still prove the authoritative catalog endpoint.
- **Saab:** current first-party page exposes ~500 openings directly, including cyber/security jobs; backend is intentionally left unknown.
- **Northrop Grumman:** first-party search is live; no ATS assumption is made.
- **Shell:** `jobs.shell.com/search-jobs` is a directly searchable first-party catalog; no ATS vendor inference is required yet.
- **bp:** current careers/listing is live; backend remains unresolved.
- **Coinbase:** first-party positions catalog is current and exposes openings by department/location; do not assume historical Greenhouse.
- **Wiz:** current first-party careers page explicitly identifies official publishing surfaces but not an ATS vendor.
- **Schneider Electric:** current first-party careers is verified, backend left unresolved until current handoff/network evidence is captured.

## New quality rule for all future batches

Every new row must include enough evidence to answer **one of these**:

1. `Which current first-party link directly hands off to this ATS?`
2. `Which live ATS board/API currently contains this employer's vacancies?`
3. `Which first-party statement explicitly identifies the recruiting platform?`
4. If none: `UNVERIFIED/PROBABLE`, never `VERIFIED`.

This is now the authoritative census policy.

---

## Audit v2 — operational verification standard

From this point onward, the ledger uses a stricter evidence model. Older `VERIFIED` labels from Batches 1-6 are **legacy** until explicitly re-audited here or in later audit sections.

### Evidence states

- `FIRST_PARTY_VERIFIED`: the current company-controlled careers/apply surface itself exposes enough evidence to identify the operational platform/backend family.
- `TECHNICALLY_VERIFIED`: the current operational surface exposes a distinctive platform contract/signature (host/path/query/schema) that is sufficient to identify the backend family, even if the company does not name the vendor.
- `PROBABLE`: strong current evidence exists, but one cheap direct fingerprint/probe is still required before automatic adapter selection.
- `UNVERIFIED`: current first-party careers surface is known, but the operational backend family is not established.

### Automation gate

Only `FIRST_PARTY_VERIFIED` and `TECHNICALLY_VERIFIED` mappings may enter an automatic FAST_PATH queue. `PROBABLE` and `UNVERIFIED` must first pass a direct fingerprint/probe. Historical ATS reputation or old indexed postings are not sufficient.

### Re-audited examples — 2026-09-02

| Employer | Current direct evidence checked | Audit-v2 state | Operational consequence |
|---|---|---|---|
| Palantir | Live `jobs.lever.co/palantir` catalog returns current roles | **FIRST_PARTY_VERIFIED / Lever** | FAST_PATH allowed |
| OpenAI | Live `jobs.ashbyhq.com/openai` board resolves today | **TECHNICALLY_VERIFIED / Ashby** | FAST_PATH allowed; catalog probe still required |
| Anthropic | Live `job-boards.greenhouse.io/anthropic` board returns current jobs | **TECHNICALLY_VERIFIED / Greenhouse** | FAST_PATH allowed |
| Adyen | Live `job-boards.greenhouse.io/adyen` board returns current jobs | **TECHNICALLY_VERIFIED / Greenhouse** | FAST_PATH allowed |
| Cloudflare | Greenhouse vanity board currently redirects to Cloudflare first-party careers | **PROBABLE / Greenhouse operational API must be probed directly** | Do not auto-FAST_PATH solely from the vanity redirect |
| SpaceX | Greenhouse vanity board currently redirects to SpaceX careers | **PROBABLE / Greenhouse operational API must be probed directly** | Direct Boards API proof required |
| Anduril | Greenhouse vanity board currently redirects to first-party open roles | **PROBABLE / Greenhouse operational API must be probed directly** | Direct Boards API proof required |
| Okta | Current public Greenhouse board could not be reliably validated through the web fetch used in this audit | **PROBABLE** | Direct API probe required |
| Tenable | Current public Greenhouse board could not be reliably validated through the web fetch used in this audit | **PROBABLE** | Direct API probe required |
| Datadog | Current public Greenhouse board could not be reliably validated through the web fetch used in this audit | **PROBABLE** | Direct API probe required |

This is intentionally stricter than the earlier ledger. A redirect from an ATS vanity URL to a first-party site does **not** prove that the structured ATS API remains the authoritative catalog. The future census tool should probe the structured endpoint itself.

---

## Tier-S mapping — Batch 8 (strict audit-v2 method)

This batch extends the census from 85 to **95 employers**. The table deliberately separates current first-party surface verification from backend identification.

| Priority | Employer | Current careers / jobs surface | Operational ATS / backend | Evidence state | Adapter in supplied ZIP | Path | Next action |
|---:|---|---|---|---|---:|---|---|
| 86 | Vodafone Group | `https://jobs.vodafone.com/careers?domain=vodafone.com` plus `careers.vodafone.com` | Eightfold-style careers contract (`/careers?domain=...&pid=...`, resume-match/recommendation UI); platform vendor not first-party-declared in evidence captured | **TECHNICALLY_VERIFIED platform signature; vendor attribution PROBABLE** | No Eightfold adapter | **ADAPTER_NEEDED / RESOLVER_LIGHT** | Inspect network calls once; if Eightfold API contract matches Ericsson/other tenants, build reusable Eightfold adapter |
| 87 | Eni | `https://jobs.eni.com/.../sites/CX_1004/job/<id>` | **Oracle Recruiting Cloud / Candidate Experience**; Eni first-party candidate manual explicitly documents ORC flow | **FIRST_PARTY_VERIFIED** | **Yes — Oracle Recruiting Cloud** | **FAST_PATH** | Resolve all active CX site IDs and probe structured Oracle catalog |
| 88 | Nokia | `https://jobs.nokia.com/en/sites/CX_1/job/<id>` | **Oracle Recruiting Cloud / Candidate Experience** contract | **TECHNICALLY_VERIFIED** | **Yes — Oracle Recruiting Cloud** | **FAST_PATH** | Probe `CX_1` and validate complete active catalog + descriptions |
| 89 | Ferrari | `https://jobs.ferrari.com/` with current job URLs like `/job/<city>-<slug>/<numeric-id>/` | SAP SuccessFactors Recruiting Marketing strongly indicated by current RMK-style first-party surface and URL contract | **PROBABLE** | **Yes — SuccessFactors RMK** | FAST_PATH candidate | One direct SuccessFactors fingerprint/API probe before automatic selection |
| 90 | Volvo Group | `https://jobs.volvogroup.com/`, current jobs `/job/<slug>/<numeric-id>/?feedId=361555` | SAP SuccessFactors Recruiting Marketing strongly indicated by current RMK-style catalog/search contract | **PROBABLE** | **Yes — SuccessFactors RMK** | FAST_PATH candidate | Direct RMK fingerprint/probe; verify all group brands share the same catalog |
| 91 | NetApp | `https://jobs.netapp.com/`, current paginated first-party catalog with `/go/...` and classic job-search structure | SAP SuccessFactors Recruiting Marketing strongly indicated by current RMK-style surface | **PROBABLE** | **Yes — SuccessFactors RMK** | FAST_PATH candidate | Direct RMK API/signature probe before auto-selection |
| 92 | Equinix | `https://careers.equinix.com/jobs/search` | Modern first-party careers platform; current search exposes UUID-style job URLs, requisition IDs, facets and complete catalog, but backend family not proven | **UNVERIFIED backend** | No proven adapter match | **RESOLVER_NEEDED** | Inspect search XHR/GraphQL/API; prefer structured current first-party datasource over ATS guessing |
| 93 | HSBC | `https://mycareer.hsbc.com/en_GB/external/SearchJobs/` | First-party custom/hosted pipeline search (`pipelineOffset`, `pipelineRecordsPerPage`, `pipelineId`); underlying vendor not safely identified | **UNVERIFIED backend** | No proven adapter match | **RESOLVER_NEEDED** | Network fingerprint; determine whether platform is reusable across other banks before adapter work |
| 94 | TotalEnergies | `https://careers.totalenergies.com/` | Current first-party global careers/search surface; backend family not established from direct evidence in this audit | **UNVERIFIED backend** | No proven match | **RESOLVER_NEEDED** | Follow “all offers” flow and inspect structured search/detail requests |
| 95 | F5 | `https://www.f5.com/company/careers` / current F5 career listings | Current first-party careers ecosystem confirmed, but historical vendor references are insufficient to freeze a backend today | **UNVERIFIED backend** | No proven match | **RESOLVER_NEEDED** | Direct current search/apply fingerprint; ignore historical Recsolu/other vendor evidence unless still operational |

### Batch-8 conclusions

This strict batch gives:

```text
2 clear FAST_PATH       Eni, Nokia
3 FAST_PATH candidates  Ferrari, Volvo Group, NetApp
1 reusable-platform candidate  Vodafone / Eightfold-style
4 genuine backend-unknown      Equinix, HSBC, TotalEnergies, F5
```

The important lesson is that a visually recognizable career template is useful for prioritization but **not enough for automatic adapter selection**. Ferrari/Volvo/NetApp therefore remain `PROBABLE` until a direct structured-platform probe succeeds.

### Direct evidence notes — Batch 8

#### Vodafone
- Current operational surface: `https://jobs.vodafone.com/careers?domain=vodafone.com...`
- Current catalog exposes ~1,000 jobs, search facets and resume-based job recommendations.
- The URL/search contract is materially similar to the Ericsson/Eightfold-style surface already observed, making Eightfold a reusable-platform hypothesis rather than a company-specific hack.

#### Eni
- Current first-party job URLs use `/sites/CX_1004/job/<id>`.
- Eni publishes a candidate manual explicitly documenting its Oracle Recruiting Cloud (`ORC`) external application flow.
- This is sufficient for FIRST_PARTY_VERIFIED Oracle Recruiting Cloud classification.

#### Nokia
- Current jobs use `/en/sites/CX_1/job/<id>` on `jobs.nokia.com`.
- This is the distinctive Oracle Recruiting Cloud Candidate Experience route shape already supported by the project.

#### Ferrari
- Current first-party catalog and job detail pages are live on `jobs.ferrari.com`.
- The page/search/job-route morphology matches SAP SuccessFactors RMK, but this batch did not capture a first-party SAP endpoint or tenant identifier; therefore PROBABLE only.

#### Volvo Group
- Current first-party catalog exposes hundreds of jobs and current detail URLs with large numeric IDs and `feedId`.
- Surface morphology matches SAP SuccessFactors RMK, but direct backend proof is still required.

#### NetApp
- Current first-party jobs surface exposes classic paginated result pages (`Results 1-50`, `/go/...`, searchable categories) characteristic of RMK deployments.
- Direct structured-platform proof is still required before FAST_PATH.

#### Equinix
- Current first-party search is unusually data-rich: requisition ID, category, location, workplace type and job type are already exposed in catalog results.
- This may permit a high-quality first-party structured adapter even if the underlying ATS is never needed.

#### HSBC
- Current first-party hosted search supports controlled pagination (`pipelineOffset`, `pipelineRecordsPerPage`) and pipeline IDs.
- Do not map this to an ATS vendor by visual similarity; inspect requests first.

#### TotalEnergies
- Current first-party global careers site is active and explicitly identifies itself as the official vacancy source.
- Operational backend remains intentionally UNKNOWN until the “all offers” data flow is inspected.

#### F5
- Historical F5 recruiting URLs referenced other vendors, but historical platform evidence is not accepted under audit v2.
- Current operational search/apply flow must be fingerprinted directly.

---

## Census status after Batch 8

```text
Total employers in ledger: 95
```

Do not compute a trusted percentage of `FAST_PATH` from the legacy batches yet. The only trustworthy automation-ready count is the subset that has passed audit v2. The next work should combine:

1. continue to ~100-110 employers;
2. perform cheap direct API/fingerprint audits on high-value legacy FAST_PATH candidates;
3. specifically test recurring platform hypotheses: Greenhouse vanity/API, SuccessFactors RMK, Eightfold, BrassRing/Talent Gateway;
4. only then freeze the initial census and rank new adapter development by number/value of employers unlocked.

---

## Audit v2 expansion — 2026-09-02

This section continues the retroactive audit with the stricter rule introduced after Batch 7. The evidence state below overrides older legacy labels for the named employers.

### Newly audited legacy rows

| Employer | Direct current evidence | Audit-v2 state | Operational consequence |
|---|---|---|---|
| CrowdStrike | Multiple current requisitions resolve directly on `crowdstrike.wd5.myworkdayjobs.com/.../crowdstrikecareers/...` and expose Workday requisition IDs such as `R29824`, `R29358`, `R29440` | **TECHNICALLY_VERIFIED / Workday** | FAST_PATH allowed; next gate is adapter catalog probe/completeness, not ATS discovery |
| Palantir | Current complete job catalog is live on `jobs.lever.co/palantir`, with current internship/new-grad/security roles | **TECHNICALLY_VERIFIED / Lever** | FAST_PATH allowed |
| OpenAI | Current job details resolve directly on `jobs.ashbyhq.com/openai/<uuid>` with department/location/employment metadata | **TECHNICALLY_VERIFIED / Ashby** | FAST_PATH allowed |
| Anthropic | Current live catalog resolves on `job-boards.greenhouse.io/anthropic` and exposes hundreds of active roles | **TECHNICALLY_VERIFIED / Greenhouse hosted board** | FAST_PATH allowed; Boards API catalog parity still remains the probe gate |
| Swiss Re | Current first-party catalog is live at `careers.swissre.com`, with classic paginated `go/Search-Jobs/...` surface and large numeric job IDs; Swiss Re also states its HR environment includes SAP/SuccessFactors Recruiting | **PROBABLE / SuccessFactors RMK** | Do not auto-select yet; one direct RMK fingerprint/probe required |

### Audit rule refinement

`TECHNICALLY_VERIFIED` means the current operational ATS surface itself is observed serving current employer requisitions. It does **not** mean the Research Agent adapter has already passed catalog-completeness validation for that employer.

Therefore:

```text
TECHNICALLY_VERIFIED ATS
        ↓
existing adapter
        ↓
controlled catalog probe
        ↓
CATALOG VERIFIED / FIX
```

This prevents the census from conflating “we know the ATS” with “our scanner is correct for this employer”.

---

## Tier-S mapping — Batch 9 (strict audit-v2, employers 96–105)

This batch extends the ledger from 95 to **105 employers**. Current first-party/operational evidence was checked before assigning a backend family. Unknown vendor attribution remains UNKNOWN rather than being inferred from visual similarity.

| Priority | Employer | Current careers / jobs surface | Operational ATS / backend | Evidence state | Adapter in supplied ZIP | Path | Next action |
|---:|---|---|---|---|---:|---|---|
| 96 | Leonardo | `https://leonardocompany.wd3.myworkdayjobs.com/LeonardoCareerSite` | **Workday (`wd3`)**, current requisitions expose IDs such as `R0029206` / `R0030941` | **TECHNICALLY_VERIFIED** | **Yes — Workday** | **FAST_PATH** | Derive tenant/site (`leonardocompany` / `LeonardoCareerSite`) and run complete catalog probe |
| 97 | Honeywell Technologies | `https://careers.honeywell.com/en/sites/Honeywell/jobs` | **Oracle Recruiting Cloud / Candidate Experience vanity domain**; current routes are `/en/sites/Honeywell/job/<numeric-id>` | **TECHNICALLY_VERIFIED; first-party careers link also confirmed by Honeywell FAQ** | **Yes — Oracle Recruiting Cloud** | **FAST_PATH** | Resolve ORC REST/catalog contract behind vanity host and test description/ID coverage; keep spun-off Honeywell Aerospace as a separate employer/tenant |
| 98 | Boeing | `https://jobs.boeing.com/` | Rich first-party global job-search surface with pagination, facets and current job metadata; backend vendor not directly proven in this audit | **FIRST_PARTY_VERIFIED surface / backend UNKNOWN** | No proven match | **RESOLVER_LIGHT** | Inspect search XHR/network once; do not assign Radancy solely from page morphology |
| 99 | L3Harris Technologies | `https://careers.l3harris.com/en/search-jobs` | Rich first-party global catalog, currently ~129–132 result pages and explicit Security/IT categories; vendor attribution not directly proven | **FIRST_PARTY_VERIFIED surface / backend UNKNOWN** | No proven match yet | **RESOLVER_LIGHT** | Fingerprint search/detail network; Radancy/TalentBrew is a hypothesis only until proven |
| 100 | Munich Re | `https://careers.munichre.com/en/search-jobs` | First-party group catalog with facets, pagination and >1,000 group results; underlying hosted-platform vendor not directly proven | **FIRST_PARTY_VERIFIED surface / backend UNKNOWN** | No proven match yet | **RESOLVER_LIGHT** | Inspect structured search calls; test whether one backend covers Munich Re + HSB + ERGO/NewRe scopes cleanly |
| 101 | Swiss Re | `https://careers.swissre.com/go/Search-Jobs/2744601/` | **SuccessFactors RMK strongly indicated** by current RMK-style catalog and Swiss Re's own SAP/SuccessFactors Recruiting environment | **PROBABLE** | **Yes — SuccessFactors RMK** | FAST_PATH candidate | Direct RMK fingerprint + adapter probe before automatic selection |
| 102 | AXA Group | `https://careers.axa.com/` / `https://jobs.axa.com/careers-home/` | Current first-party global search/career platform; backend family not established from direct evidence | **FIRST_PARTY_VERIFIED surface / backend UNKNOWN** | No proven match | **RESOLVER_NEEDED** | Inspect search XHR/API and determine whether all AXA entities share one operational catalog |
| 103 | Rheinmetall | `https://www.rheinmetall.com/en/career/career-overview` | First-party career ecosystem/current-vacancy flow verified; backend family not frozen | **FIRST_PARTY_VERIFIED surface / backend UNKNOWN** | No proven match | **RESOLVER_NEEDED** | Follow “current job vacancies” into operational search and fingerprint backend before any ATS label |
| 104 | TikTok / ByteDance | `https://careers.tiktok.com/position` | **Custom TikTok careers platform**, currently exposes ~4,135 open roles, structured facets and graduate/intern filters | **FIRST_PARTY_VERIFIED custom surface** | No | **RESOLVER_NEEDED** | Inspect search/detail API; likely high-value custom adapter because one solution may cover TikTok/ByteDance ecosystems |
| 105 | Arm | `https://careers.arm.com/search-jobs` | First-party hosted job-search platform with pagination/facets and current Security/Product Security categories; backend vendor not directly proven | **FIRST_PARTY_VERIFIED surface / backend UNKNOWN** | No proven match | **RESOLVER_LIGHT** | Fingerprint network/API; page morphology alone must not be used to label Radancy |

### Batch-9 conclusions

The batch produces:

```text
2 direct existing-adapter FAST_PATH
  Leonardo  -> Workday
  Honeywell -> Oracle Recruiting Cloud

1 existing-adapter candidate
  Swiss Re  -> probable SuccessFactors RMK

7 current first-party catalogs requiring only backend fingerprinting
  Boeing, L3Harris, Munich Re, AXA, Rheinmetall, TikTok/ByteDance, Arm
```

This is exactly the distinction the audit was intended to expose: many `RESOLVER_*` rows no longer require broad web research. Their current catalogs are already known and healthy; the unresolved task is often just **one network/API fingerprint**.

### Direct evidence notes — Batch 9

#### Leonardo
- Current requisitions are served directly from `leonardocompany.wd3.myworkdayjobs.com/LeonardoCareerSite`.
- Current pages expose standard Workday fields: locations, time type, posted date and requisition IDs such as `R0029206` and `R0030941`.
- This is automation-grade ATS identification; no resolver should be invoked before trying the existing Workday adapter.

#### Honeywell Technologies
- Honeywell's own FAQ links candidates to `https://careers.honeywell.com/en/sites/Honeywell`.
- Current job routes are `.../en/sites/Honeywell/job/<id>` and expose Job Identification, category, posting date, locations and schedule.
- This is the Oracle Candidate Experience route family. Treat Honeywell Technologies and the separately spun-off Honeywell Aerospace as separate employers/tenants; do not merge their lifecycle records.

#### Boeing
- Current first-party search exposes ~900+ positions in sampled location views and dozens of structured categories, including Cybersecurity and Product Security.
- Because the data surface is already rich, resolver work should first seek the search datasource rather than jump to detail-page HTML scraping.

#### L3Harris
- Current first-party search exposes around 129–132 pages and explicit `Security`, `Information Technology`, internship/new-grad and engineering facets.
- The surface resembles known hosted career platforms, but audit v2 forbids vendor attribution from morphology alone.

#### Munich Re
- Current group search exposes 1,500+ aggregate results in broad views and supports company/job-level/category filters.
- A reusable structured endpoint here could cover multiple Munich Re group brands, so backend fingerprinting has high leverage.

#### Swiss Re
- Current first-party search exposes 300+ jobs in audited views and large stable numeric job identifiers.
- Swiss Re's own current job content states its global HR environment includes SAP/SuccessFactors and Recruiting, reinforcing—but not independently proving—the RMK hypothesis.

#### AXA
- Current global careers surface and `jobs.axa.com/careers-home/` are active and expose centralized category/search experiences.
- Underlying platform remains intentionally UNKNOWN until requests are inspected.

#### Rheinmetall
- Current first-party career ecosystem is active and links to live vacancies/job alerts.
- No ATS is assigned yet because the operational search backend was not directly identified in this pass.

#### TikTok / ByteDance
- Current first-party TikTok search exposes roughly 4,135 roles plus job-type, program, category and location facets.
- Because catalog scale is large, a structured search API is strongly preferable to HTML pagination and could justify a reusable custom-family adapter.

#### Arm
- Current search exposes ~300 results in one audited view, pagination and categories including Security and Product Security.
- Treat as a high-priority light fingerprint: current catalog is healthy; only the structured datasource/platform family remains unknown.

---

## Census status after Batch 9 + audit expansion

```text
Total employers in ledger: 105
```

### Automation-grade audited examples now established

At minimum, the following rows have current direct ATS/platform evidence strong enough to skip broad resolver discovery and proceed straight to an employer probe with an existing adapter:

```text
CrowdStrike -> Workday
Leonardo    -> Workday
Palantir    -> Lever
OpenAI      -> Ashby
Anthropic   -> Greenhouse hosted board
Eni         -> Oracle Recruiting Cloud
Nokia       -> Oracle Recruiting Cloud
Honeywell   -> Oracle Recruiting Cloud
```

This list is deliberately **not** the full set of likely fast paths; it is the subset explicitly promoted under audit-v2 evidence in the working ledger so far.

### Next audit priorities

The next pass should prioritize old high-value FAST_PATH claims whose direct ATS/API proof is still incomplete:

1. NVIDIA -> Workday tenant/catalog proof;
2. Cloudflare -> Greenhouse Boards API proof despite vanity redirect;
3. Datadog -> Greenhouse Boards API proof;
4. SpaceX -> Greenhouse Boards API proof;
5. Anduril -> Greenhouse Boards API proof;
6. Okta -> Greenhouse current catalog/API proof;
7. Tenable -> Greenhouse current catalog/API proof;
8. Airbus -> Workday tenant/catalog proof;
9. Deutsche Bank -> Workday tenant/catalog proof;
10. Siemens -> Avature current operational catalog proof.

In parallel, continue the employer census beyond 105, but never let new-row volume replace retroactive validation.

---

## Audit v2 — parallel revalidation pass B (2026-09-02)

This section overrides older legacy labels for the named employers. A current ATS-hosted board or current first-party ATS job detail was observed directly during this pass.

| Employer | Current operational evidence | Audit-v2 state | Automation consequence |
|---|---|---|---|
| Airbus | Current requisitions resolve on `ag.wd3.myworkdayjobs.com/...` and expose Workday requisition IDs such as `JR10435916`, `JR10433321`, `JR10412750` | **TECHNICALLY_VERIFIED / Workday** | FAST_PATH allowed; run Workday catalog probe |
| Deutsche Bank | Current requisitions resolve on `db.wd3.myworkdayjobs.com/.../DBWebsite/...` with IDs such as `R0405747`, `R0381827` | **TECHNICALLY_VERIFIED / Workday** | FAST_PATH allowed |
| Vanta | Multiple current jobs resolve on `jobs.ashbyhq.com/vanta/<uuid>` with department/location/type metadata | **TECHNICALLY_VERIFIED / Ashby** | FAST_PATH allowed |
| Anduril Industries | Current 2026 jobs resolve directly on `job-boards.greenhouse.io/andurilindustries/jobs/<id>` | **TECHNICALLY_VERIFIED / Greenhouse hosted board** | FAST_PATH allowed; Boards API parity remains probe gate |
| Tenable | Current complete board is live on `job-boards.greenhouse.io/tenableinc`, with current job inventory and departments including Security Engineering/Product Development | **TECHNICALLY_VERIFIED / Greenhouse hosted board** | FAST_PATH allowed |
| Cloudflare | Current individual jobs resolve on `job-boards.greenhouse.io/cloudflare/jobs/<id>`, but the board root redirects to first-party Cloudflare Careers | **TECHNICALLY_VERIFIED at job-detail level / Greenhouse; catalog root behavior changed** | FAST_PATH candidate: direct Greenhouse Boards API catalog probe required before automatic board-token trust |
| SpaceX | Greenhouse board root currently redirects to `spacex.com/careers`; current direct board-catalog proof was not captured in this pass | **PROBABLE / historical Greenhouse, current catalog not yet re-proven** | Do not auto-select yet; probe Boards API directly |
| Spotify | Current complete catalog is live on `jobs.lever.co/spotify` with current openings and Lever filtering | **TECHNICALLY_VERIFIED / Lever** | FAST_PATH allowed |
| Visa | Current SmartRecruiters company surface `careers.smartrecruiters.com/Visa` is live and first-party branded, though one audited render returned no postings | **TECHNICALLY_VERIFIED platform family / SmartRecruiters; catalog completeness unverified** | Adapter selection allowed only for a controlled SmartRecruiters API/catalog probe; do not mark catalog PASS yet |

### Audit-B evidence URLs

- Airbus: `https://ag.wd3.myworkdayjobs.com/en-US/Airbus/job/Export-Control-Due-Diligence-Manager_JR10435916`
- Deutsche Bank: `https://db.wd3.myworkdayjobs.com/de-DE/DBWebsite/job/Off-cycle-Internship-Program-2026-O-A-Investment-Banking---Milan--f-m-x-_R0405747`
- Vanta: `https://jobs.ashbyhq.com/vanta/c752a8a1-5832-4d2a-a8c5-8b8308d6a7e2`
- Anduril: `https://job-boards.greenhouse.io/andurilindustries/jobs/4802146007`
- Tenable: `https://job-boards.greenhouse.io/tenableinc`
- Cloudflare current job detail: `https://job-boards.greenhouse.io/cloudflare/jobs/7736431`
- SpaceX board root observed redirect: `https://job-boards.greenhouse.io/spacex`
- Spotify: `https://jobs.lever.co/spotify`
- Visa: `https://careers.smartrecruiters.com/Visa`

### Important audit consequence

A hosted ATS **job detail** and a hosted ATS **complete catalog** are now tracked separately. For example, Cloudflare can be technically verified as using Greenhouse for current job details while still requiring a Boards API probe before we trust the old board token as a complete operational catalog. This prevents a redirecting vanity board from being mistaken for catalog completeness.

---

## Tier-S / high-value mapping — Batch 10 (strict audit-v2, employers 106–113)

This batch prioritizes high-value cloud, developer-platform and frontier-AI employers. Only current operational evidence is used for ATS assignment.

| Priority | Employer | Current careers / jobs surface | Operational ATS / backend | Evidence state | Adapter in supplied ZIP | Path | Next action |
|---:|---|---|---|---|---:|---|---|
| 106 | Twilio | `https://job-boards.greenhouse.io/twilio` | **Greenhouse**, current hosted board with ~100+ active jobs and security roles | **TECHNICALLY_VERIFIED** | **Yes — Greenhouse** | **FAST_PATH** | Probe Boards API token `twilio`; compare record count/IDs/descriptions with hosted board |
| 107 | Red Hat | `https://redhat.wd5.myworkdayjobs.com/Jobs` | **Workday**, current requisitions such as `R-054536` | **TECHNICALLY_VERIFIED** | **Yes — Workday** | **FAST_PATH** | Derive `wd5 / redhat / Jobs` tuple and run complete catalog probe |
| 108 | PagerDuty | `https://job-boards.greenhouse.io/pagerduty` | **Greenhouse**, live current board | **TECHNICALLY_VERIFIED** | **Yes — Greenhouse** | **FAST_PATH** | Probe board token `pagerduty` |
| 109 | Mistral AI | `https://jobs.ashbyhq.com/mistral.ai` | **Ashby**, current job details with UUIDs | **TECHNICALLY_VERIFIED** | **Yes — Ashby** | **FAST_PATH** | Probe Ashby tenant `mistral.ai`; verify full catalog and descriptions |
| 110 | Cohere | `https://jobs.ashbyhq.com/cohere` | **Ashby**, current internship/job details served directly from Ashby | **TECHNICALLY_VERIFIED** | **Yes — Ashby** | **FAST_PATH** | Probe Ashby tenant `cohere` |
| 111 | Perplexity | `https://jobs.ashbyhq.com/Perplexity` | **Ashby**, current job details served directly from Ashby | **TECHNICALLY_VERIFIED** | **Yes — Ashby** | **FAST_PATH** | Probe tenant case/slug carefully (`Perplexity` observed); verify catalog identity |
| 112 | Figma | `https://job-boards.greenhouse.io/figma` | **Greenhouse**, multiple current job applications including 2026/2027 engineering roles | **TECHNICALLY_VERIFIED** | **Yes — Greenhouse** | **FAST_PATH** | Probe board token `figma`; verify first-party career parity |
| 113 | GitHub | `https://www.github.careers/careers-home/jobs` | Current first-party GitHub Careers catalog is live; operational ATS/backend not directly identified in this pass | **FIRST_PARTY_VERIFIED surface / backend UNKNOWN** | No proven match | **RESOLVER_LIGHT** | Inspect US/global listings links and network/API; because GitHub is Microsoft-owned, do not assume Microsoft ATS without direct evidence |

### Batch-10 evidence notes

#### Twilio
- Current Greenhouse board is directly live and exposes well over 100 jobs in audited snapshots.
- Current security-relevant sections include Offensive Security, Security Risk, Incident Response and AI Security.
- This is sufficient to skip generic portal discovery and proceed directly to the existing Greenhouse adapter.

#### Red Hat
- Current Red Hat requisitions resolve directly on `redhat.wd5.myworkdayjobs.com/en-US/Jobs/...` with Workday requisition IDs.
- Existing Workday adapter should be tried before any browser resolver.

#### PagerDuty
- Current board is directly live on Greenhouse and exposes a complete categorized catalog.
- Existing Greenhouse adapter is the correct first action.

#### Mistral AI
- Current jobs use `jobs.ashbyhq.com/mistral.ai/<uuid>` and expose location, employment type, department and full descriptions.
- This is a high-value European AI employer that becomes a zero-new-adapter fast path.

#### Cohere
- Current 2026 internship/job detail is served directly from `jobs.ashbyhq.com/cohere/<uuid>`.
- Treat as Ashby fast path; employer-level completeness still requires probe.

#### Perplexity
- Current jobs are served from `jobs.ashbyhq.com/Perplexity/<uuid>`.
- Keep the observed tenant casing until the adapter/API probe determines canonical normalization.

#### Figma
- Multiple current applications are directly live on `job-boards.greenhouse.io/figma/jobs/<id>`, including software-engineering internships and security-engineering interest areas.
- Existing Greenhouse adapter should be sufficient unless API parity fails.

#### GitHub
- The current first-party GitHub Careers surface is live with US/global listings, categories and locations.
- No ATS family is assigned yet. Ownership by Microsoft is not evidence that GitHub uses Microsoft Careers' backend.

---

## Census status after Batch 10 + parallel audit

```text
Total employers in ledger: 113
```

### Newly automation-grade in this pass

```text
Airbus          -> Workday
Deutsche Bank   -> Workday
Vanta           -> Ashby
Anduril         -> Greenhouse
Tenable         -> Greenhouse
Spotify         -> Lever
Twilio          -> Greenhouse
Red Hat         -> Workday
PagerDuty       -> Greenhouse
Mistral AI      -> Ashby
Cohere          -> Ashby
Perplexity      -> Ashby
Figma           -> Greenhouse
```

Cloudflare and Visa are deliberately kept one gate below catalog verification; SpaceX is downgraded to a direct-API recheck because its old Greenhouse board root currently redirects to the first-party career site.

### Reusable-platform signal after 113 employers

The audit increasingly supports a two-stage onboarding architecture:

```text
1. deterministic ATS fingerprint / direct-current-evidence check
2. existing adapter controlled probe
3. only failures/unknowns -> resolver
```

The recurring families with existing adapters are already dominant among newly audited fast paths: Greenhouse, Workday, Ashby and Lever. New adapter development should therefore remain focused on repeatedly observed unsupported families such as BrassRing/Talent Gateway, Oracle Taleo and potentially Eightfold—not on one-off company-specific code.

### Next parallel work

1. Continue audit-v2 on NVIDIA, Datadog, Okta, Bosch, Siemens and the remaining old FAST_PATH rows.
2. Directly test Greenhouse Boards API tokens for Cloudflare and SpaceX rather than relying on hosted-board redirects.
3. Continue census toward 125–130 employers, prioritizing AI/cloud/security and finance employers with high job-search value.
4. Start a platform-frequency table once at least ~30 legacy rows have passed audit-v2; count only audited platform evidence, never legacy guesses.

---

## Audit-v2 C — legacy fast-path revalidation + unsupported-family confirmation

**Audit date:** 2026-09-02

This pass continues the stricter rule introduced after the initial census: only current operational evidence can promote a mapping to automation-grade. Historical vendor associations are not enough.

| Employer | Current evidence checked | Audit-v2 result | Automation consequence |
|---|---|---|---|
| NVIDIA | Multiple current requisitions resolve on `nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite` with live IDs such as `JR2024364`, `JR2024664`, `JR2021114` | **TECHNICALLY_VERIFIED / Workday** | FAST_PATH allowed; derive `wd5 / nvidia / NVIDIAExternalCareerSite` and probe |
| Bosch Group | Current country career boards are served on `careers.smartrecruiters.com/BoschGroup/...`; the pages explicitly call SmartRecruiters Bosch's partner and expose live openings | **TECHNICALLY_VERIFIED / SmartRecruiters** | FAST_PATH allowed; determine the correct global/company identifiers and verify catalog union/coverage |
| Siemens | Siemens itself states that recruitment runs through the **Avature job portal** at `jobs.siemens.com/careers`; current job links use `/careers/job/<numeric-id>` | **FIRST_PARTY_VERIFIED / Avature** | FAST_PATH allowed with existing Avature adapter; probe catalog and Siemens-vs-Healthineers scope carefully |
| Okta | Current job details continue to resolve directly on `job-boards.greenhouse.io/okta/jobs/<id>` and are Okta-branded | **TECHNICALLY_VERIFIED at job-detail level / Greenhouse** | FAST_PATH candidate; direct Boards API catalog probe is still the completeness gate |
| Cloudflare | Multiple current 2026 job details resolve directly on `job-boards.greenhouse.io/cloudflare/jobs/<id>`; hosted board root behavior remains vanity/redirect-like | **TECHNICALLY_VERIFIED at detail level / Greenhouse** | Keep one gate below catalog PASS; direct `boards-api` token probe required |
| Datadog | First-party careers surface is current and exposes hundreds of open positions; current Greenhouse linkage is strongly corroborated, but this pass did not capture a fresh first-party/hosted Greenhouse catalog response | **FIRST_PARTY_VERIFIED surface / Greenhouse remains PROBABLE pending direct API probe** | Do not auto-PASS platform mapping yet; one Boards API request can settle it cheaply |
| UBS | Current jobs are directly served on `jobs.ubs.com/TGnewUI/...` with `partnerid=25008`, `siteid=...`, search result counts and job IDs | **TECHNICALLY_VERIFIED / Talent Gateway (BrassRing-family)** | **ADAPTER_NEEDED**; strong reusable-platform candidate, especially because IBM/other large employers may share the family |
| Salesforce | Current first-party job details are live on `careers.salesforce.com/en/jobs/JR...` with stable requisition IDs and full descriptions | **FIRST_PARTY_VERIFIED custom surface / backend still UNKNOWN** | RESOLVER_LIGHT; inspect search/detail network before assigning ATS |

### Audit-C evidence

- NVIDIA current Workday job: `https://nvidia.wd5.myworkdayjobs.com/nvidiaexternalcareersite/job/US-Remote/Senior-Staff-Site-Reliability-Engineer---Compute-Core-Engineering_JR2024364-1`
- Bosch SmartRecruiters: `https://careers.smartrecruiters.com/BoschGroup/bulgaria`
- Siemens first-party Avature statement: `https://www.siemens.com/lt-lt/company/about/fraud-prevention-brazil/`
- Siemens current Avature-style job path examples: `https://jobs.siemens.com/careers/job/563156131830054`
- Okta current Greenhouse detail: `https://job-boards.greenhouse.io/okta/jobs/7892592`
- Cloudflare current Greenhouse detail: `https://job-boards.greenhouse.io/cloudflare/jobs/8118855`
- Datadog current first-party careers: `https://careers.datadoghq.com/`
- UBS current global search surface: `https://jobs.ubs.com/TGnewUI/Search/Home/HomeWithPreLoad?LinkID=3107&PageType=searchResults&SearchType=linkquery&partnerid=25008&siteid=5012`
- Salesforce current first-party detail: `https://careers.salesforce.com/en/jobs/jr338691/deal-strategy-and-pricing-manager/`

### Audit-C consequence

`Workday`, `SmartRecruiters` and `Avature` are now backed by stronger current evidence for major Tier-S employers. `Talent Gateway / BrassRing` has also crossed the threshold from "interesting historical platform" to **current repeated unsupported family worth an adapter feasibility study**.

For Greenhouse vanity-board cases, platform identity and catalog completeness remain separate gates. A live job detail proves that Greenhouse participates in the current flow; only a direct Boards API catalog probe proves that the board token is suitable as the authoritative discovery source.

---

## Tier-S / high-value mapping — Batch 11 (employers 114–118)

This batch adds high-value AI/data/developer-platform companies where current hosted ATS evidence is directly observable. All five can bypass generic resolver discovery and start from an existing adapter.

| Priority | Employer | Current careers / jobs surface | Operational ATS / backend | Evidence state | Adapter in supplied ZIP | Path | Next action |
|---:|---|---|---|---|---:|---|---|
| 114 | Scale AI | `https://job-boards.greenhouse.io/scaleai` | **Greenhouse**, live hosted board with ~200 current openings | **TECHNICALLY_VERIFIED** | **Yes — Greenhouse** | **FAST_PATH** | Probe board token `scaleai`; verify count, IDs and descriptions |
| 115 | Notion | `https://jobs.ashbyhq.com/notion` | **Ashby**, current 2026 job and internship details with UUIDs | **TECHNICALLY_VERIFIED** | **Yes — Ashby** | **FAST_PATH** | Probe tenant `notion`; high-value because current GRC/security roles are present |
| 116 | Harvey | `https://jobs.ashbyhq.com/harvey` | **Ashby**, current job details with UUIDs, departments, locations and compensation | **TECHNICALLY_VERIFIED** | **Yes — Ashby** | **FAST_PATH** | Probe tenant `harvey`; verify full catalog |
| 117 | Linear | `https://jobs.ashbyhq.com/Linear` / `.../linear/<uuid>` | **Ashby**, current hosted jobs; tenant casing varies in surfaced URLs | **TECHNICALLY_VERIFIED** | **Yes — Ashby** | **FAST_PATH** | Probe canonical tenant/slug and normalize casing only after API response |
| 118 | Databricks | Greenhouse-hosted Databricks job application/catalog surfaces | **Greenhouse**, board identity `databricks`; large hosted catalog observed | **TECHNICALLY_VERIFIED platform family; freshness of one surfaced catalog snapshot is older than this audit** | **Yes — Greenhouse** | **FAST_PATH candidate** | Perform direct Boards API probe now; if current catalog responds, promote immediately to automation-grade |

### Batch-11 evidence notes

#### Scale AI
- Current `job-boards.greenhouse.io/scaleai` catalog is live and has recently shown roughly 200+ openings.
- This is a direct Greenhouse fast path; no company-specific resolver logic is justified.

#### Notion
- Current Ashby details include a **Governance, Risk, and Compliance Intern (Fall 2026)** and current engineering/trust roles.
- This is particularly valuable for the project because it demonstrates that the existing Ashby path covers exactly the kind of early-career security opportunity we are searching for.

#### Harvey
- Multiple current jobs resolve directly on `jobs.ashbyhq.com/harvey/<uuid>` including Milan roles.
- Existing Ashby adapter should be tried before any other discovery.

#### Linear
- Current jobs resolve on Ashby with both `Linear` and `linear` casing appearing in surfaced URLs.
- The adapter/probe should determine canonical tenant behavior rather than hard-coding casing assumptions.

#### Databricks
- Databricks has a Greenhouse board identity and large structured catalog evidence.
- Because the strongest catalog snapshot surfaced in this pass is not as fresh as the other Batch-11 evidence, the ledger deliberately requires a direct one-request Boards API check before granting final audit-v2 automation-grade status.

### Batch-11 evidence URLs

- Scale AI: `https://job-boards.greenhouse.io/scaleai`
- Notion GRC internship: `https://jobs.ashbyhq.com/notion/6ccbc30c-2de0-4395-af14-3641cd15961b`
- Notion Trust engineering: `https://jobs.ashbyhq.com/notion/66236b7e-2905-4a93-84a5-ed036a1a6581`
- Harvey: `https://jobs.ashbyhq.com/harvey/ebf00b72-4693-4894-b540-5f82a60fdbdc`
- Linear: `https://jobs.ashbyhq.com/Linear/1d652292-04d9-405c-8101-578efd020e94/`
- Databricks board identity: `https://job-boards.greenhouse.io/embed/job_app?for=databricks&token=7464169002`

---

## Census status after Batch 11 + Audit-v2 C

```text
Total employers in ledger: 118
```

### Newly strengthened / automation-grade in this pass

```text
NVIDIA       -> Workday
Bosch Group  -> SmartRecruiters
Siemens      -> Avature
Scale AI     -> Greenhouse
Notion       -> Ashby
Harvey       -> Ashby
Linear       -> Ashby
```

### One-cheap-probe candidates

```text
Cloudflare   -> Greenhouse detail VERIFIED; Boards API catalog probe pending
Okta         -> Greenhouse detail VERIFIED; Boards API catalog probe pending
Datadog      -> first-party current; direct Greenhouse API proof pending
Databricks   -> Greenhouse family established; fresh direct API proof pending
SpaceX       -> historical/current Greenhouse signals conflict at board-root level; direct API probe pending
```

### Unsupported platform with growing ROI

```text
Talent Gateway / BrassRing
  -> UBS current operational evidence confirmed
  -> IBM and other historical/current large-enterprise signals make a reusable adapter worth investigating
```

### Current architectural takeaway

The census is now sufficiently mature to distinguish three very different workloads:

```text
A. CURRENT ATS VERIFIED + EXISTING ADAPTER
   -> no resolver
   -> controlled probe only

B. CURRENT PLATFORM VERIFIED + ADAPTER MISSING
   -> build platform adapter once
   -> reuse

C. FIRST-PARTY SURFACE ONLY / BACKEND UNKNOWN
   -> resolver/network inspection
```

The next highest-value work should continue in parallel:

1. keep expanding toward ~130 employers;
2. finish direct API proofs for the Greenhouse vanity-board candidates;
3. continue audit-v2 of remaining legacy FAST_PATH rows;
4. fingerprint the repeated unsupported families (BrassRing/Talent Gateway, Eightfold, Taleo) before writing any company-specific resolver code.

---

## Audit-v2 D — direct-current revalidation + catalog-surface checks

**Audit date:** 2026-09-02

This pass keeps the stricter automation rule: a current ATS detail proves platform participation; a live current board/catalog proves a stronger discovery path; only a controlled API/catalog probe can finally establish employer-level completeness.

| Employer | Current evidence checked | Audit-v2 result | Automation consequence |
|---|---|---|---|
| Cloudflare | Multiple current 2026 job details are live on `job-boards.greenhouse.io/cloudflare/jobs/<id>` including applications accepting candidates into Nov 2026 | **TECHNICALLY_VERIFIED / Greenhouse current operational detail surface** | Existing Greenhouse adapter is the correct first probe; catalog completeness still requires direct Boards API count/ID comparison |
| Okta | Current Okta-branded Greenhouse job details remain live on `job-boards.greenhouse.io/okta/jobs/<id>` | **TECHNICALLY_VERIFIED / Greenhouse current operational detail surface** | Existing Greenhouse adapter first; do not mark catalog PASS until direct board/API probe |
| Datadog | Current first-party careers page exposes hundreds of live openings by function/region; Greenhouse API/board identity remains strongly corroborated externally but not directly fetched in this environment during this pass | **FIRST_PARTY_VERIFIED / Greenhouse candidate remains pending one direct API probe** | Keep one gate below automation-grade catalog verification |
| SpaceX | Current evidence is split: historical/current domestic postings are tracked with Greenhouse slug `spacex`, while a separate live `spacexglobal` Greenhouse board currently exposes international roles | **TECHNICALLY_VERIFIED / Greenhouse family, multi-board scope likely** | Do not treat one token as the whole SpaceX catalog; probe `spacex` and `spacexglobal`, union by stable job ID, compare against first-party careers |
| Databricks | Current third-party verification trails continue to identify Greenhouse slug `databricks` and first-party URLs with `gh_jid` | **TECHNICALLY_CORROBORATED / Greenhouse; direct fresh catalog request still pending** | Existing Greenhouse adapter first; require one fresh API response before catalog PASS |

### Audit-D evidence URLs

- Cloudflare current Greenhouse details: `https://job-boards.greenhouse.io/cloudflare/jobs/8030327`, `https://job-boards.greenhouse.io/cloudflare/jobs/7053411`
- Okta current Greenhouse detail: `https://job-boards.greenhouse.io/okta/jobs/7892592`
- Datadog current first-party catalog: `https://careers.datadoghq.com/`
- SpaceX international Greenhouse board: `https://job-boards.greenhouse.io/spacexglobal`
- SpaceX Greenhouse API slug corroboration: `https://boards-api.greenhouse.io/v1/boards/spacex/jobs`
- Databricks Greenhouse API/job provenance example: `https://boards-api.greenhouse.io/v1/boards/databricks/jobs/8608900002`

### Audit-D correction: multi-board employers

SpaceX introduces a new ledger rule:

```text
one employer
!=
one ATS tenant/board necessarily
```

A company can expose different geographic/legal hiring inventories through separate board tokens. The future mapping schema therefore needs `operational_sources[]` rather than a single scalar `ats_tenant_or_token` whenever evidence shows multiple active catalogs.

---

## Tier-S / high-value mapping — Batch 12 (employers 119–126, strict audit-v2)

This batch adds AI infrastructure, developer platforms and security-heavy SaaS employers. All entries below are based on current hosted ATS/job evidence, not historical vendor lists.

| Priority | Employer | Current careers / jobs surface | Operational ATS / backend | Evidence state | Adapter in supplied ZIP | Path | Next action |
|---:|---|---|---|---|---:|---|---|
| 119 | Ramp | `https://jobs.ashbyhq.com/ramp` | **Ashby**, current jobs with UUIDs, departments, location/workplace metadata and compensation | **TECHNICALLY_VERIFIED** | **Yes — Ashby** | **FAST_PATH** | Probe Ashby tenant `ramp`; verify complete catalog and descriptions |
| 120 | Grafana Labs | `https://job-boards.greenhouse.io/grafanalabs` | **Greenhouse**, live current board with 100+ openings | **TECHNICALLY_VERIFIED** | **Yes — Greenhouse** | **FAST_PATH** | Probe token `grafanalabs`; preserve location variants as distinct source jobs |
| 121 | ElevenLabs | `https://jobs.ashbyhq.com/elevenlabs` | **Ashby**, multiple current roles incl. Italy/Europe with UUIDs and full metadata | **TECHNICALLY_VERIFIED** | **Yes — Ashby** | **FAST_PATH** | Probe tenant `elevenlabs`; normalize observed slug casing only after API response |
| 122 | Tailscale | `https://job-boards.greenhouse.io/tailscale` | **Greenhouse**, live board with ~60+ jobs and current security-engineering roles | **TECHNICALLY_VERIFIED** | **Yes — Greenhouse** | **FAST_PATH** | Probe token `tailscale`; very high-value cyber employer |
| 123 | Discord | `https://job-boards.greenhouse.io/discord` plus `discordinternational` | **Greenhouse**, current domestic/main board plus a separate international board | **TECHNICALLY_VERIFIED / multi-board** | **Yes — Greenhouse** | **FAST_PATH** | Probe both `discord` and `discordinternational`; union/dedup by native source ID |
| 124 | Censys | `https://job-boards.greenhouse.io/Censys` | **Greenhouse**, live board with current AppSec, threat-hunting and security-research roles | **TECHNICALLY_VERIFIED** | **Yes — Greenhouse** | **FAST_PATH** | Probe canonical token/casing (`Censys` observed); verify API token normalization |
| 125 | ClickHouse | `https://job-boards.greenhouse.io/clickhouse` | **Greenhouse**, live board with ~175 openings | **TECHNICALLY_VERIFIED** | **Yes — Greenhouse** | **FAST_PATH** | Probe token `clickhouse`; verify descriptions and regional duplicates |
| 126 | Commvault | `https://job-boards.greenhouse.io/commvault` | **Greenhouse**, current hosted catalog with engineering/product/security-related roles | **TECHNICALLY_VERIFIED** | **Yes — Greenhouse** | **FAST_PATH** | Probe token `commvault`; compare against Commvault first-party careers if vanity layer exists |

### Batch-12 evidence notes

#### Ramp
Current Ashby jobs expose UUID identity, location, employment type, workplace mode, department and compensation. This is a clean existing-adapter case.

#### Grafana Labs
The current Greenhouse board is live and repeatedly shows a triple-digit catalog. No autonomous discovery is justified before trying the existing Greenhouse adapter.

#### ElevenLabs
Multiple current roles are served directly from Ashby, including Italy-specific and Europe-wide roles. This is particularly valuable for the user's geography.

#### Tailscale
The current board exposes security-specific jobs such as `Security Infrastructure Engineer` and `Security Software Engineer`, making this both technically easy and high-value for P0 CYBER.

#### Discord
Discord demonstrates the same multi-board issue seen at SpaceX: the main `discord` board and `discordinternational` board may represent different inventories. The mapping must support source unions rather than assuming one board token per corporate employer.

#### Censys
Current board includes AppSec, SOC/threat-hunting and security-research roles. This should be a priority fast-path employer for the CYBER dataset.

### Batch-12 evidence URLs

- Ramp: `https://jobs.ashbyhq.com/ramp`
- Grafana Labs: `https://job-boards.greenhouse.io/grafanalabs`
- ElevenLabs: `https://jobs.ashbyhq.com/elevenlabs/20a29846-f8f5-483c-a3cb-52f14c525366`
- Tailscale: `https://job-boards.greenhouse.io/tailscale`
- Discord: `https://job-boards.greenhouse.io/discord`
- Discord international: `https://job-boards.greenhouse.io/discordinternational`
- Censys: `https://job-boards.greenhouse.io/Censys`
- ClickHouse: `https://job-boards.greenhouse.io/clickhouse`
- Commvault: `https://job-boards.greenhouse.io/commvault`

---

## Census status after Batch 12 + Audit-v2 D

```text
Total employers in ledger: 126
```

### Newly automation-grade in this pass

```text
Ramp          -> Ashby
Grafana Labs  -> Greenhouse
ElevenLabs    -> Ashby
Tailscale     -> Greenhouse
Discord       -> Greenhouse (multi-board)
Censys        -> Greenhouse
ClickHouse    -> Greenhouse
Commvault     -> Greenhouse
```

### Audit items strengthened but still requiring catalog-completeness probe

```text
Cloudflare    -> Greenhouse current detail surface verified
Okta          -> Greenhouse current detail surface verified
Datadog       -> first-party current; direct GH catalog fetch pending
Databricks    -> Greenhouse strongly corroborated; direct fresh catalog fetch pending
SpaceX        -> Greenhouse family verified, but likely multi-board (`spacex` + `spacexglobal`)
```

### New schema implication discovered

The mapping should eventually model:

```text
employer
  -> operational_sources[]
       - platform
       - tenant/token/site
       - geography/scope
       - canonical/first-party relationship
       - evidence_state
       - last_verified_at
```

rather than forcing every employer into exactly one ATS token. This matters for SpaceX and Discord already and is likely to recur in multinational enterprises.

### Next parallel work

1. Continue census toward 135–140 employers.
2. Continue audit-v2 of legacy Greenhouse/Workday/SuccessFactors/Oracle mappings.
3. Prioritize direct catalog probes for Cloudflare, Okta, Datadog, Databricks, SpaceX and the new multi-board cases.
4. Start a frequency table based **only on audit-v2 evidence**, separating existing-adapter families from unsupported repeated families.
5. Keep BrassRing/Talent Gateway, Eightfold and Taleo as the leading reusable-adapter candidates unless the audited frequency table changes the ranking.

---

## Tier-S / high-value mapping — Batch 13 (employers 127–135, strict audit-v2)

**Audit date:** 2026-09-02

This batch continues the strict rule: only current hosted ATS/job evidence is accepted for automation-grade mapping. No historical ATS directory alone is sufficient.

| Priority | Employer | Current careers / jobs surface | Operational ATS / backend | Evidence state | Adapter in supplied ZIP | Path | Next action |
|---:|---|---|---|---|---:|---|---|
| 127 | Huntress | `https://job-boards.greenhouse.io/huntress` | **Greenhouse**, live current board with ~30–40 openings and dedicated Security / SOC / Product Research sections | **TECHNICALLY_VERIFIED** | **Yes — Greenhouse** | **FAST_PATH** | Probe token `huntress`; high-priority P0 CYBER employer because the current catalog already contains SOC/security-research roles |
| 128 | Chainguard | `https://job-boards.greenhouse.io/chainguard` | **Greenhouse**, live current board with ~80+ openings, including Information Security and Product Security departments | **TECHNICALLY_VERIFIED** | **Yes — Greenhouse** | **FAST_PATH** | Probe token `chainguard`; preserve department metadata because it is highly useful for CYBER validation |
| 129 | Verkada | `https://job-boards.greenhouse.io/verkada` | **Greenhouse**, live current board with ~280+ openings | **TECHNICALLY_VERIFIED** | **Yes — Greenhouse** | **FAST_PATH** | Probe token `verkada`; beware physical-security/product roles versus information-security roles at AI classification stage |
| 130 | Socket | `https://jobs.ashbyhq.com/socket` | **Ashby**, current jobs with UUID identities and Security department metadata | **TECHNICALLY_VERIFIED** | **Yes — Ashby** | **FAST_PATH** | Probe tenant `socket`; strong cybersecurity / software-supply-chain target |
| 131 | Material Security | `https://jobs.ashbyhq.com/materialsecurity` | **Ashby**, current UUID job records and full descriptions | **TECHNICALLY_VERIFIED** | **Yes — Ashby** | **FAST_PATH** | Probe tenant `materialsecurity`; useful email/cloud-security employer |
| 132 | Relativity Space | `https://job-boards.greenhouse.io/relativity` | **Greenhouse**, current hosted job details under stable numeric job IDs | **TECHNICALLY_VERIFIED** | **Yes — Greenhouse** | **FAST_PATH** | Probe token `relativity`; compare full board against first-party Relativity careers before catalog PASS |
| 133 | Physical Intelligence | `https://jobs.ashbyhq.com/physicalintelligence` | **Ashby**, current UUID jobs across research, software, hardware and operations | **TECHNICALLY_VERIFIED** | **Yes — Ashby** | **FAST_PATH** | Probe tenant `physicalintelligence`; mainly AI target for later phases, but easy to onboard now |
| 134 | Browserbase | `https://jobs.ashbyhq.com/browserbase` | **Ashby**, current UUID jobs with department/location/compensation metadata | **TECHNICALLY_VERIFIED** | **Yes — Ashby** | **FAST_PATH** | Probe tenant `browserbase`; relevant AI/developer-infrastructure target |
| 135 | Cognition | `https://jobs.ashbyhq.com/cognition` | **Ashby**, current UUID job records for Devin/Cognition | **TECHNICALLY_VERIFIED** | **Yes — Ashby** | **FAST_PATH** | Probe tenant `cognition`; mainly future AI/SWE target, but no resolver needed |

### Batch-13 direct evidence notes

#### Huntress
The current Greenhouse board is live and contains dedicated Security categories including SOC management/analysis, threat detection/response and security research. This is an unusually high-value FAST_PATH for P0 CYBER.

#### Chainguard
The current board exposes dedicated `Information Security` and `Product Security` sections with roles such as Security Engineer, Senior Security Analyst (Governance and Trust), Product Security Engineer and Vulnerability Management Engineer. This is another high-priority P0 CYBER fast path.

#### Verkada
The current board is large and live. Because Verkada's business also includes physical-security products, CYBER membership must remain a semantic LLM decision; ATS detection alone must never equate all Verkada jobs with cybersecurity.

#### Socket / Material Security
Both currently serve jobs directly from Ashby with stable UUID identity and rich metadata. These require no portal-resolution reasoning before trying the existing Ashby adapter.

#### Relativity Space
Current job applications resolve directly on Greenhouse under board slug `relativity`. Employer-level catalog completeness still requires the normal board/API probe and first-party comparison.

#### Physical Intelligence / Browserbase / Cognition
All three currently expose live Ashby UUID job records. They are more relevant to future AI/SWE expansion than P0 CYBER, but onboarding them is mechanically cheap and demonstrates that the census is useful beyond the first vertical.

### Batch-13 evidence URLs

- Huntress: `https://job-boards.greenhouse.io/huntress`
- Chainguard: `https://job-boards.greenhouse.io/chainguard`
- Verkada: `https://job-boards.greenhouse.io/verkada`
- Socket: `https://jobs.ashbyhq.com/socket/983b52ce-83ad-4af5-a494-65fbfbd7e38e`
- Material Security: `https://jobs.ashbyhq.com/materialsecurity/004c4e76-037b-45ec-ac09-1d526a7f47fb`
- Relativity Space: `https://job-boards.greenhouse.io/relativity/jobs/8468809002`
- Physical Intelligence: `https://jobs.ashbyhq.com/physicalintelligence/031e9b1e-6e58-4c81-b608-3cfda0514082`
- Browserbase: `https://jobs.ashbyhq.com/browserbase/bcbf0fb9-2405-497b-bbc9-e09d8f7a4963`
- Cognition: `https://jobs.ashbyhq.com/cognition/811c3f5a-b26d-4162-b49b-93890a91794d`

---

## Audit-v2 E — frequency table based only on explicit v2 evidence

**Audit date:** 2026-09-02  
**Important:** this is a **minimum verified count**, not the final 135-employer distribution. It counts unique employers that already have an explicit `FIRST_PARTY_VERIFIED` or `TECHNICALLY_VERIFIED` v2 record in this ledger. Legacy mappings that have not yet been re-audited are excluded rather than guessed.

After Batch 13, the v2-audited subset contains at least **63 unique employers**. The distribution is:

| Platform family | Explicitly audited employers (minimum) | Adapter already in supplied ZIP? | Operational implication |
|---|---:|---:|---|
| Greenhouse | **23** | Yes | Highest-volume fast path; prioritize automated token/board probes and multi-board union handling |
| Ashby | **15** | Yes | Second-largest verified family; straightforward fast path with UUID identities |
| Workday | **6** | Yes | Existing adapter has strong ROI; tenant/site derivation and completeness validation remain employer-specific |
| Oracle Recruiting Cloud | **3** | Yes | Existing adapter; site/CX identifiers must be resolved per employer |
| Lever | **2** | Yes | Existing adapter; cheap fast path |
| SmartRecruiters | **2** | Yes | Existing adapter; verify company identifiers/global-vs-regional scope |
| Avature | **1** | Yes | Existing adapter; Siemens is explicit first-party proof |
| Eightfold ecosystem | **1** | No | Reusable adapter candidate if direct catalog API is confirmed across Ericsson/Vodafone-like tenants |
| Talent Gateway / BrassRing family | **1** | No | Strong adapter candidate because UBS is technically verified and IBM/other large employers may share it |
| Custom / backend still unknown | **9** | No proven common adapter | Resolver/fingerprint queue; do not assume one implementation per employer |
| Custom Google Careers RPC | **1** | V24 implementation prepared | Separate verified custom-platform case |

### Frequency-table interpretation

The audited data now supports a stronger architectural conclusion than the earlier rough estimates:

```text
63 explicitly audited employers

44+ already map to one of the dominant supported families
(Greenhouse + Ashby + Workday alone)

unsupported repeated-platform work
is concentrated in a much smaller set:
- Eightfold
- Talent Gateway / BrassRing
- Taleo (legacy evidence; needs v2 proof)
- genuinely custom portals
```

Therefore the preferred resolution order remains:

```text
1. deterministic fingerprint
2. existing supported adapter probe
3. reusable unsupported-platform adapter
4. resolver AI only for the residual custom/unknown set
```

### Important audit correction on Greenhouse vanity boards

A current Greenhouse job-detail URL proves that Greenhouse participates in the operational hiring flow, but **does not by itself prove that one board token is the complete employer catalog**. Cloudflare, SpaceX and similar cases remain subject to a direct Boards API count/ID comparison, and multinational employers may require multiple active board tokens.

---

## Census status after Batch 13 + Audit-v2 E

```text
Total employers in ledger: 135
Explicitly audit-v2 employers: at least 63
```

### Highest-value new P0 CYBER fast paths from Batch 13

```text
Huntress     -> Greenhouse
Chainguard   -> Greenhouse
Socket       -> Ashby
Material Sec -> Ashby
```

### Next parallel work

1. Continue census toward 145–150 employers.
2. Continue audit-v2 of legacy high-value mappings, especially Datadog, Cloudflare catalog completeness, Okta catalog completeness, SpaceX multi-board completeness, Porsche/BMW/Volkswagen SuccessFactors claims, and finance/defense mappings not yet v2.
3. Start direct no-LLM catalog probes for the v2 Greenhouse/Ashby fast-path cohort; ATS discovery is already solved for these employers.
4. Fingerprint Eightfold on Ericsson/Vodafone and Talent Gateway/BrassRing on UBS before writing a general resolver.
5. Keep frequency counts based only on explicit v2 evidence; never fold legacy `VERIFIED` rows into automation statistics until re-audited.

---

## Tier-S / high-value mapping — Batch 14 (employers 136–142, strict audit-v2)

**Audit date:** 2026-09-02

This batch deliberately mixes new high-value employers with direct audit-v2 verification. A first-party careers page is enough to prove the employer surface exists, but **not** enough to assign an ATS family. FAST_PATH is granted only where a current hosted ATS/job surface is directly evidenced.

| Priority | Employer | Current careers / jobs surface | Operational ATS / backend | Evidence state | Adapter in supplied ZIP | Path | Next action |
|---:|---|---|---|---|---:|---|---|
| 136 | Armis Security | `https://job-boards.greenhouse.io/armissecurity` | **Greenhouse**, current live board `armissecurity` with current job IDs and full descriptions | **TECHNICALLY_VERIFIED** | **Yes — Greenhouse** | **FAST_PATH** | Probe board token `armissecurity`; high-value P0 CYBER employer |
| 137 | Roche | `https://roche.wd3.myworkdayjobs.com/roche-ext` | **Workday**, live `wd3` tenant/site with current requisitions such as `202608-122299` | **TECHNICALLY_VERIFIED** | **Yes — Workday** | **FAST_PATH** | Derive/confirm tenant tuple and run full structured catalog probe |
| 138 | Sierra | `https://jobs.ashbyhq.com/Sierra` | **Ashby**, current UUID job records under Sierra tenant | **TECHNICALLY_VERIFIED** | **Yes — Ashby** | **FAST_PATH** | Probe Ashby tenant; useful future AI target and potentially security-adjacent roles |
| 139 | Recorded Future | `https://job-boards.greenhouse.io/recordedfuture` | **Greenhouse**, live current board with Intelligence Security / Threat Intelligence / Cyber Operations departments | **TECHNICALLY_VERIFIED** | **Yes — Greenhouse** | **FAST_PATH** | Probe token `recordedfuture`; very high-value P0 CYBER employer |
| 140 | N26 | `https://n26.com/en-eu/careers` | First-party catalog currently exposes ~60+ positions; `gh_jid` appears in current careers URLs, suggesting Greenhouse participation, but no current board/API catalog was directly proven in this audit | **FIRST_PARTY_VERIFIED / ATS PROBABLE** | Not automation-grade yet | **RESOLVER_LIGHT / FINGERPRINT** | Inspect first-party job links/network and test any Greenhouse token directly before FAST_PATH |
| 141 | 1Password | `https://1password.com/careers` | Current first-party careers site with live open-position entry point; operational ATS/backend not proven from first-party/current hosted ATS evidence in this audit | **FIRST_PARTY_VERIFIED / BACKEND UNKNOWN** | No proven match | **RESOLVER_LIGHT** | Follow current open-position links and fingerprint datasource; do not infer historical ATS |
| 142 | Darktrace | `https://www.darktrace.com/careers` | Current first-party careers surface with Software Engineering & Research, Cyber Analysis, IT/Internal Security and other career families; backend remains unproven | **FIRST_PARTY_VERIFIED / BACKEND UNKNOWN** | No proven match | **RESOLVER_LIGHT** | Inspect `Explore opportunities` destination/network and identify structured source before building anything |

### Batch-14 direct evidence notes

#### Armis Security — Greenhouse verified
The current hosted board `job-boards.greenhouse.io/armissecurity` is live and exposes current job records with stable numeric IDs, location, description and application form. Current examples include AI/security-platform engineering and cyber-security customer roles. This is automation-grade evidence for the Greenhouse family; employer-level catalog completeness still requires the normal API/first-party parity probe.

#### Roche — Workday verified
Current Roche jobs are hosted directly on `roche.wd3.myworkdayjobs.com/roche-ext` and expose Workday requisition IDs, locations, posting dates and complete descriptions. This is a direct Workday FAST_PATH, not a historical ATS inference.

#### Sierra — Ashby verified
Current Sierra postings resolve directly to `jobs.ashbyhq.com/Sierra/<uuid>`, providing stable UUID vacancy identity and full job content. Existing Ashby support should be tried before any custom resolver work.

#### Recorded Future — Greenhouse verified
The current `recordedfuture` Greenhouse board is live with dozens of openings and departments explicitly relevant to P0 CYBER, including Intelligence Security, Threat Intelligence and Cyber Operations. This is one of the highest-value newly verified fast paths.

#### N26 — deliberately not promoted
The current first-party N26 careers page exposes dozens of open positions and currently accepts URLs carrying a `gh_jid` parameter. That is a meaningful Greenhouse hint, but **a parameter is not sufficient evidence that one live Greenhouse board is the complete current catalog**. N26 remains a cheap fingerprint task until the underlying board/API is directly demonstrated.

#### 1Password — first party yes, ATS unknown
The current 1Password careers page is clearly live and links to open positions, but this audit did not obtain a current hosted ATS/API surface. Because 1Password is a high-value cybersecurity employer, it should receive a lightweight datasource inspection rather than a guessed ATS assignment.

#### Darktrace — first party yes, ATS unknown
Darktrace's current careers site is live and exposes explicit Software Engineering & Research, Cyber Analysis, IT/Internal Security and other tracks. The operational jobs datasource was not directly proven in this audit, so it stays out of FAST_PATH until network/redirect inspection identifies it.

### Batch-14 evidence URLs

- Armis: `https://job-boards.greenhouse.io/armissecurity`
- Roche: `https://roche.wd3.myworkdayjobs.com/en-US/roche-ext/job/Junior-Patient-Journey-Partner-HCC_202608-122299`
- Sierra: `https://jobs.ashbyhq.com/Sierra/c66b30fc-9588-4699-85c1-2166b23b8778`
- Recorded Future: `https://job-boards.greenhouse.io/recordedfuture`
- N26: `https://n26.com/en-eu/careers`
- 1Password: `https://1password.com/careers`
- Darktrace: `https://www.darktrace.com/careers`

---

## Audit-v2 F — updated frequency table after Batch 14

**Audit date:** 2026-09-02  
**Counting rule:** only explicit audit-v2 records are counted. Legacy `VERIFIED` rows remain excluded until individually re-audited.

Starting from the 63-employer audit-v2 subset in Audit-v2 E, Batch 14 adds seven newly audited employers. The explicit audit-v2 subset is therefore now at least **70 unique employers**.

| Platform family | Explicitly audited employers (minimum) | Adapter already in supplied ZIP? | Operational implication |
|---|---:|---:|---|
| Greenhouse | **25** | Yes | Dominant verified family; prioritize automatic board-token/API probes and multi-board union support |
| Ashby | **16** | Yes | Strong fast path; stable UUID identity |
| Workday | **7** | Yes | Strong enterprise fast path; tenant/site derivation remains employer-specific |
| Oracle Recruiting Cloud | **3** | Yes | Existing adapter; resolve site/CX identifiers per employer |
| Lever | **2** | Yes | Existing adapter |
| SmartRecruiters | **2** | Yes | Existing adapter |
| Avature | **1** | Yes | Existing adapter |
| Eightfold ecosystem | **1** | No | Reusable adapter/fingerprint candidate |
| Talent Gateway / BrassRing family | **1** | No | Reusable adapter candidate |
| Custom / backend still unknown | **12** | No proven common adapter | Resolver-light/full resolver queue; includes the newly audited N26/1Password/Darktrace cases until proven otherwise |
| Custom Google Careers RPC | **1** | V24 implementation prepared | Separate custom-platform case |

### What the audited numbers now say

At least:

```text
70 explicit audit-v2 employers

48 = Greenhouse + Ashby + Workday alone
   = ~69% of the audited subset
```

This remains strikingly stable even as the audited sample grows. The architectural conclusion is therefore getting stronger rather than weaker:

```text
known ATS detection + existing adapter
must be the default path

resolver AI
must be the exception path
```

### Newly promoted automation-grade fast paths

```text
Armis Security   -> Greenhouse
Roche            -> Workday
Sierra           -> Ashby
Recorded Future  -> Greenhouse
```

### Newly explicit lightweight fingerprint queue

```text
N26       -> Greenhouse hint (`gh_jid`), but catalog not proven
1Password -> first-party careers verified, backend unknown
Darktrace -> first-party careers verified, backend unknown
```

### Next parallel work after Batch 14

1. Continue census toward 150 employers.
2. Continue audit-v2 of legacy high-value entries instead of trusting historical mappings.
3. Directly probe Greenhouse Boards API for Cloudflare, SpaceX, Okta, Datadog, Databricks and N26 candidates.
4. Fingerprint 1Password and Darktrace through current first-party open-position links/network calls.
5. Audit the remaining enterprise families where a reusable adapter may unlock multiple employers: Eightfold, Talent Gateway/BrassRing and Taleo.
6. Begin generating a machine-readable version of only the audit-v2 rows (`CSV/JSON`) once the ledger reaches ~150 employers; legacy rows must not leak into automatic portal routing.

---

## Batch 14 — census 143–150 + audit-v2 closure pass

**Audit date:** 2026-09-02

This batch keeps the v2 rule: an employer is automation-grade only when current operational evidence is strong enough to identify the source family. Historical ATS claims alone are not sufficient.

| # | Employer | Current careers / operational surface | Audit-v2 backend result | Evidence grade | Existing adapter | Path | Next action |
|---:|---|---|---|---|---:|---|---|
| 143 | Reddit | `https://job-boards.greenhouse.io/reddit` | Greenhouse, board `reddit` | **TECHNICALLY_VERIFIED** — live current board with ~150 active jobs | Yes | **FAST_PATH** | Controlled Greenhouse API probe + parity check with Reddit careers |
| 144 | Netlify | `https://www.netlify.com/careers/` and live `job-boards.greenhouse.io/netlify` | Greenhouse, board `netlify` | **TECHNICALLY_VERIFIED** — current Greenhouse catalog mirrors current first-party openings | Yes | **FAST_PATH** | Greenhouse API probe; tiny catalog makes parity easy |
| 145 | Vercel | `https://job-boards.greenhouse.io/vercel` | Greenhouse, board `vercel` | **TECHNICALLY_VERIFIED** — live board currently exposes ~80–90 roles | Yes | **FAST_PATH** | Controlled Greenhouse API probe |
| 146 | CoreWeave | `https://www.coreweave.com/careers` | Greenhouse strongly active; first-party URLs expose `gh_jid`, and a Greenhouse CoreWeave catalog exists | **TECHNICALLY_VERIFIED family / catalog parity pending** | Yes | **FAST_PATH_CANDIDATE** | Resolve exact active board scope(s), then compare counts with first-party regional surfaces |
| 147 | Robinhood | `https://careers.robinhood.com/` and `job-boards.greenhouse.io/robinhood/...` | Greenhouse, board `robinhood` | **TECHNICALLY_VERIFIED** — current Greenhouse job pages render Robinhood's live careers UI | Yes | **FAST_PATH** | Greenhouse API probe + first-party count parity |
| 148 | Airbnb | `https://careers.airbnb.com/` | First-party custom catalog currently exposes ~168+ roles; backend family not proven in this audit | **FIRST_PARTY_VERIFIED / backend UNVERIFIED** | No proven match | **RESOLVER_LIGHT** | Inspect current search/detail datasource; do not infer Greenhouse from historical references |
| 149 | Dropbox | `https://jobs.dropbox.com/` / current first-party hiring | Greenhouse is strongly reported and current applications are consistent with it, but this audit did not capture a live first-party-to-board proof | **PROBABLE** | Yes if confirmed | **FAST_PATH_CANDIDATE** | One direct board/API + first-party apply-link check before automation |
| 150 | Lyft | `https://www.lyft.com/careers` plus multiple current Greenhouse subsidiary/operational boards | Greenhouse exists for active Lyft-related surfaces (`lyft-av-depot`, Freenow), but one authoritative global Lyft catalog is not proven | **FIRST_PARTY_VERIFIED / MULTI_SOURCE_UNRESOLVED** | Partial | **RESOLVER_LIGHT** | Enumerate operational sources and legal entities before choosing catalog union |

### Batch-14 result

```text
5 clear/near-clear existing-adapter paths:
  Reddit        -> Greenhouse
  Netlify       -> Greenhouse
  Vercel        -> Greenhouse
  Robinhood     -> Greenhouse
  CoreWeave     -> Greenhouse family confirmed, parity still required

1 probable fast path:
  Dropbox       -> likely Greenhouse, direct proof still required

2 resolver-light / multi-source cases:
  Airbnb
  Lyft
```

The census has now reached **150 employers**.

---

## Audit-v2 closure notes — 2026-09-02

### 1Password — upgraded to TECHNICALLY_VERIFIED / FAST_PATH

Current operational jobs are directly live on:

`https://jobs.ashbyhq.com/1password/<uuid>`

The current board exposes real 1Password positions including Authorization, Security/PSIRT and other Technology roles. The operational ATS is therefore **Ashby**, slug `1password`.

**Status:** `TECHNICALLY_VERIFIED -> FAST_PATH`.

### Cloudflare — Greenhouse family upgraded, full-catalog parity still a probe gate

Current 2026 Cloudflare jobs are directly rendered on `job-boards.greenhouse.io/cloudflare/jobs/<id>`, including current Security Platform roles and ordinary non-security openings. This is enough to establish **Greenhouse as a live operational source**.

However, the v2 ledger continues to distinguish:

```text
platform/source family verified
!=
complete catalog parity verified
```

**Status:** `TECHNICALLY_VERIFIED Greenhouse -> FAST_PATH_CANDIDATE`; promote to catalog-verified only after the Boards API count is compared with the current Cloudflare first-party vacancy surface.

### Okta — Greenhouse upgraded to TECHNICALLY_VERIFIED / FAST_PATH_CANDIDATE

Okta's current first-party job catalog is live and current Okta technology documentation/job descriptions explicitly identify **Greenhouse as the ATS** in its recruiting stack. Current tracked requisitions retain stable `gh_jid` identities.

**Status:** Greenhouse family `TECHNICALLY_VERIFIED`; exact complete-board parity remains a controlled-probe gate.

### Datadog — Greenhouse family evidence strengthened

Current/known operational job pages use the Datadog Greenhouse board and external technical source catalogs continue to identify the structured endpoint `boards-api.greenhouse.io/v1/boards/datadog/jobs`. The first-party careers surface remains live with hundreds of jobs.

**Status:** `TECHNICALLY_VERIFIED family / CATALOG_PARITY_PENDING` rather than unconditional catalog VERIFIED.

### Databricks — Greenhouse family strongly confirmed, freshness caveat retained

Greenhouse board pages for `databricks` expose a catalog in the high hundreds with full department/location structure. Because the directly surfaced Greenhouse snapshots available in this audit are not as fresh as the strictest first-party evidence, keep catalog completeness as `PENDING_PROBE` rather than pretending it is current-perfect.

**Status:** `TECHNICALLY_VERIFIED family -> FAST_PATH_CANDIDATE`.

### N26 — keep PROBABLE, do not auto-route yet

The first-party N26 careers page currently exposes ~60–70 live vacancies and accepts `gh_jid` query parameters, which is a meaningful Greenhouse fingerprint. This is still insufficient to prove the exact authoritative Greenhouse board and full parity.

**Status:** remains `PROBABLE Greenhouse -> DIRECT_FINGERPRINT_REQUIRED`.

### Snyk — custom/current frontend remains unresolved

The old Greenhouse assumption is not trusted. The current Snyk first-party `all-jobs` experience is JavaScript-driven and must be fingerprinted from its current datasource.

**Status:** `RESOLVER_LIGHT`, not Greenhouse fast path.

### 1Password correction is material

Earlier it was kept unresolved because only the first-party page had been checked. Current Ashby job pages now provide direct operational proof. This is exactly why the v2 audit exists: **we upgrade when direct evidence appears, and downgrade when old evidence stops being sufficient.**

---

## Audit-v2 frequency table — minimum confirmed/candidate counts after 150 employers

This table counts only rows for which the v2 audit has explicit evidence in the ledger. It is deliberately conservative and is **not** a count of every legacy claim in earlier batches.

| Operational family | Audit-v2 confirmed / strong candidate employers (minimum) | Adapter currently in Research Agent | Implication |
|---|---:|---:|---|
| Greenhouse | **30+** | Yes | Dominant fast path; prioritize automated board-token validation and multi-board union support |
| Ashby | **17+** | Yes | Very strong fast path, especially AI/security startups |
| Workday | **7+** | Yes | High-value enterprise/defense/finance fast path |
| Oracle Recruiting Cloud | **3+** | Yes | Existing adapter has clear enterprise ROI |
| Lever | **2+** | Yes | Existing adapter sufficient for current confirmed set |
| SmartRecruiters | **2+** | Yes | Existing adapter sufficient; identifier discovery can be automated |
| Avature | **1+** | Yes | Existing adapter useful for Siemens-class employers |
| Eightfold ecosystem | **1+ strong + additional candidates** | No dedicated confirmed adapter | Candidate for reusable adapter/fingerprint work |
| Talent Gateway / BrassRing | **1+ strong + historical additional candidates** | No | High-priority unsupported family after direct re-audit |
| Taleo | candidate(s) | No | Build only if repeated current usage survives audit |
| Custom / backend unresolved | **15+** | N/A | Actual target pool for resolver AI |
| Google custom RPC | 1 | Yes in V24 | Example of resolver output becoming deterministic adapter |

### Architectural conclusion at 150 employers

The data now justify a concrete two-stage control plane:

```text
COMPANY
  ↓
CHEAP DETERMINISTIC ATS FINGERPRINT
  ↓
known + supported?
  ├─ YES -> DIRECT CONTROLLED PROBE
  └─ NO
       ↓
known repeated unsupported platform?
       ├─ YES -> BUILD/USE ONE REUSABLE ADAPTER
       └─ NO  -> RESOLVER AI
```

The resolver should therefore **not** be the entry point for every employer. Its queue should consist only of genuinely unresolved/custom portals after the deterministic fingerprint stage.

A second implementation requirement is now confirmed by multiple employers:

```text
Employer
  -> operational_sources[]
```

not:

```text
Employer
  -> one ATS token
```

because companies can expose separate boards by geography, subsidiary, legal entity, acquired company or recruiting surface.

---

## Next parallel audit queue

Highest-value items to close next:

1. **Cloudflare** — Boards API catalog count vs first-party careers count.
2. **Okta** — determine all live Greenhouse board identities (including regional split such as Okta JP) and union semantics.
3. **SpaceX** — identify `spacex` vs `spacexglobal` current source scopes and dedup rules.
4. **Datadog** — direct current Boards API proof + parity.
5. **Databricks** — direct current Boards API proof + parity.
6. **N26** — discover exact Greenhouse token from first-party network/apply flow.
7. **Dropbox** — direct live board/API proof.
8. **CoreWeave** — current Greenhouse board scope vs US/EU/APAC first-party regional catalogs.
9. **Eightfold candidates** — Ericsson/Vodafone and any additional current Eightfold employers.
10. **BrassRing/Talent Gateway candidates** — UBS/IBM and any others, to determine whether one new adapter has enough ROI.


---

## Batch 15 — census 151–158 + audit-v2 platform/completeness split

**Audit date:** 2026-09-02

This batch continues the stricter v2 rule and makes one distinction explicit:

```text
OPERATIONAL_PLATFORM_VERIFIED
!=
COMPLETE_CATALOG_VERIFIED
```

A live job detail or board proves that the platform is operational. It does **not** by itself prove that one board/token is the complete employer-wide catalog. Completeness is promoted only after a controlled API/feed probe and parity check against the first-party careers surface.

| # | Employer | Current operational evidence | Audit-v2 backend result | Evidence grade | Existing adapter | Path | Next action |
|---:|---|---|---|---|---:|---|---|
| 151 | HackerOne | Current jobs live at `jobs.ashbyhq.com/hackerone/<uuid>` | Ashby, slug `hackerone` | **TECHNICALLY_VERIFIED** — multiple current HackerOne roles on Ashby | Yes | **FAST_PATH** | Ashby catalog probe + first-party parity |
| 152 | Bugcrowd | Current job details live at `job-boards.greenhouse.io/bugcrowd/jobs/<id>`; board root redirects to first-party careers | Greenhouse, board `bugcrowd` is an active operational source | **TECHNICALLY_VERIFIED family / CATALOG_PARITY_PENDING** | Yes | **FAST_PATH_CANDIDATE** | Boards API probe + compare with Bugcrowd `See current openings` surface |
| 153 | Semgrep | Current/recent jobs live at `jobs.ashbyhq.com/semgrep/<uuid>` | Ashby, slug `semgrep` | **TECHNICALLY_VERIFIED** | Yes | **FAST_PATH** | Ashby catalog probe |
| 154 | Tines | Live current catalog at `job-boards.greenhouse.io/tines` with current Product Security / Security Operations roles | Greenhouse, board `tines` | **TECHNICALLY_VERIFIED** | Yes | **FAST_PATH** | Boards API probe + first-party parity |
| 155 | Delinea | Current/recent jobs live at `jobs.ashbyhq.com/delinea/<uuid>` | Ashby, slug `delinea` | **TECHNICALLY_VERIFIED** | Yes | **FAST_PATH** | Ashby catalog probe |
| 156 | Keeper Security | Current job details live at `job-boards.greenhouse.io/keepersecurity/jobs/<id>` | Greenhouse, board `keepersecurity` | **TECHNICALLY_VERIFIED family** | Yes | **FAST_PATH_CANDIDATE** | Board API count + first-party parity |
| 157 | Astranis | Current/recent job details live at `job-boards.greenhouse.io/astranis/jobs/<id>` | Greenhouse, board `astranis` | **TECHNICALLY_VERIFIED family** | Yes | **FAST_PATH_CANDIDATE** | Boards API probe |
| 158 | Nscale | Current jobs live at `job-boards.greenhouse.io/nscaleoperationsukltd/jobs/<id>` | Greenhouse, board `nscaleoperationsukltd` | **TECHNICALLY_VERIFIED** | Yes | **FAST_PATH** | Boards API probe + first-party parity |

### Batch-15 result

```text
8 employers added

clear FAST_PATH:
  HackerOne  -> Ashby
  Semgrep    -> Ashby
  Tines      -> Greenhouse
  Delinea    -> Ashby
  Nscale     -> Greenhouse

platform verified / parity still pending:
  Bugcrowd       -> Greenhouse
  Keeper Security-> Greenhouse
  Astranis       -> Greenhouse
```

The census has now reached **158 employers**.

---

## Audit-v2 parallel closure — Batch 15

### SpaceX — multi-source requirement strengthened

`spacexglobal` is a live Greenhouse board with current international roles. This proves at least one current structured operational source, but does **not** prove that it is the complete SpaceX catalog; it is explicitly scoped to international roles.

```text
SpaceX
  -> operational_sources[]
       - Greenhouse / spacexglobal / international scope
       - first-party / US-main scope still to resolve/verify
```

**Status:** `MULTI_SOURCE_VERIFIED_PARTIAL`. Do not union-close lifecycle until all required source scopes are known.

### CoreWeave — Greenhouse operational catalog strongly verified

A live Greenhouse CoreWeave catalog exposes roughly 179 jobs and includes current engineering/security roles. The platform is no longer merely historical/probable.

**Status:** `TECHNICALLY_VERIFIED Greenhouse / CATALOG_PARITY_PENDING` because the first-party employer presents regional surfaces and the authoritative union still has to be compared.

### Datadog — do not over-promote stale catalog snapshots

The observed Greenhouse catalog shape and board identity `datadog` are strong evidence of the operational family, but the surfaced full-catalog snapshots available during this audit are old enough that they cannot prove **current 2026 complete parity**.

**Status:** `TECHNICALLY_VERIFIED family / FRESH_DIRECT_API_PROBE_REQUIRED`.

### Databricks — same freshness rule

The `databricks` Greenhouse board identity is strongly evidenced and historic structured catalogs are large, but the surfaced catalog snapshots in this audit are not fresh enough to certify today's full inventory.

**Status:** `TECHNICALLY_VERIFIED family / FRESH_DIRECT_API_PROBE_REQUIRED`.

### Bugcrowd — useful redirect lesson

The Greenhouse board root currently redirects to Bugcrowd's first-party careers page, while current individual job details are still served from Greenhouse. Therefore:

```text
board-root redirect
!=
platform dead
```

Adapter/fingerprint logic must probe the structured API or current job-detail identities before downgrading a platform solely because its vanity board root redirects.

---

## Audit-v2 frequency table — conservative minimum after 158 employers

Only explicitly v2-audited rows are counted; legacy assumptions remain excluded.

| Operational family | Audit-v2 confirmed / strong candidate employers (minimum) | Existing adapter | Current implication |
|---|---:|---:|---|
| Greenhouse | **35+** | Yes | Dominant operational family; automate board-token discovery, direct API verification, and multi-board union |
| Ashby | **20+** | Yes | Second dominant family; especially strong among AI/security companies |
| Workday | **7+** | Yes | Enterprise/defense/finance fast path |
| Oracle Recruiting Cloud | **3+** | Yes | Existing adapter has confirmed enterprise value |
| Lever | **2+** | Yes | Existing adapter sufficient for verified set |
| SmartRecruiters | **2+** | Yes | Existing adapter sufficient; identifier discovery should be automated |
| Avature | **1+** | Yes | Existing adapter useful for Siemens-class employers |
| Eightfold ecosystem | **1+ strong + candidates** | No dedicated confirmed adapter | Reusable-adapter candidate after direct protocol audit |
| Talent Gateway / BrassRing | **1+ strong + candidates** | No | High-ROI unsupported family to investigate |
| Taleo | candidate(s) | No | Build only if repeated current usage survives v2 audit |
| Custom / backend unresolved | **15+** | N/A | Actual resolver-AI queue |
| Google custom RPC | 1 | Yes in V24 | Example of resolver result promoted into deterministic adapter |

### Quantitative conclusion

The dominant pattern remains stable as the sample grows. The project should optimize for:

```text
1. deterministic fingerprint
2. existing adapter
3. controlled catalog probe
4. only then unsupported-family adapter / resolver AI
```

The agentic resolver should never be asked to rediscover Greenhouse/Ashby/Workday for every employer.

---

## Next parallel work after 158

### Direct technical closure queue

1. Cloudflare — fresh Greenhouse Boards API count vs first-party count.
2. Okta — enumerate all board identities/regions and establish union semantics.
3. SpaceX — resolve US/main source in addition to verified `spacexglobal`.
4. CoreWeave — compare Greenhouse inventory against US/EU/APAC first-party surfaces.
5. Datadog — fresh direct Greenhouse API probe; stale search snapshots are insufficient.
6. Databricks — fresh direct Greenhouse API probe.
7. N26 — derive exact active Greenhouse token from first-party application/network flow.
8. Dropbox — direct live board/API proof.
9. Eightfold — audit Ericsson + Vodafone protocol once and test whether one adapter generalizes.
10. Talent Gateway / BrassRing — audit UBS + IBM protocol and estimate adapter reuse.

### Next census targets

Continue toward ~170 employers, prioritizing high-value cyber/security and infrastructure companies rather than low-value filler. Every new row must use v2 evidence grades.

---

# Batch 16 — census + audit-v2 parallel continuation (2026-09-02)

## New employers 159–166

| # | Employer | Current career / operational evidence | ATS / backend | Audit-v2 status | Existing adapter | Queue | Next action |
|---:|---|---|---|---|---:|---|---|
| 159 | Arctic Wolf | First-party careers are current; Arctic Wolf hiring FAQ explicitly says candidates apply to each job in **Workday**. Current requisitions are live on `arcticwolf.wd1.myworkdayjobs.com/External/...` with `R26_*` IDs. | Workday — tenant `arcticwolf`, site `External`, dc `wd1` | **TECHNICALLY_VERIFIED** | Yes | **FAST_PATH** | Controlled Workday catalog probe + parity with first-party careers |
| 160 | BeyondTrust | First-party careers currently embeds/openly lists jobs and a live current board exists at `job-boards.greenhouse.io/beyondtrust` with ~64–65 jobs. | Greenhouse — board `beyondtrust` | **TECHNICALLY_VERIFIED** | Yes | **FAST_PATH** | Boards API count + first-party parity |
| 161 | Cyberhaven | First-party careers current; live Ashby board at `jobs.ashbyhq.com/cyberhaven` is reachable today and current 2026 roles use Ashby UUID job URLs. | Ashby — slug `cyberhaven` | **TECHNICALLY_VERIFIED** | Yes | **FAST_PATH** | Ashby catalog probe + first-party parity |
| 162 | Aiven | First-party careers current with 38 jobs. Aiven explicitly states legitimate recruitment email may come from `@greenhouse.io` / `@eu.greenhouse.io`, strongly proving Greenhouse is part of the current recruiting stack; exact public board/API identity not captured in this audit. | Greenhouse family probable/current recruiting integration; board token still to prove | **FIRST_PARTY_VERIFIED / PLATFORM_STRONG_PROBABLE** | Yes if token resolved | **FINGERPRINT_THEN_FAST_PATH** | Follow one current apply link or inspect network, derive board token, then Boards API probe |
| 163 | Illumio | First-party careers current. Greenhouse board/application evidence exists, but the surfaced full-board snapshot is stale (~1.2y) while first-party job listings are current, so today's complete operational catalog is not yet proven. | Greenhouse historically/strongly evidenced; freshness incomplete | **FIRST_PARTY_VERIFIED / FRESH_PLATFORM_PROBE_REQUIRED** | Yes if still current | **FAST_PATH_CANDIDATE** | Resolve a current first-party Apply link and probe Greenhouse API before promotion |
| 164 | Varonis | First-party careers and dedicated `careers.varonis.com` catalog are current with departments including R&D and Threat Services; underlying ATS/vendor is not proven in this audit. | Backend unknown | **FIRST_PARTY_VERIFIED / BACKEND_UNKNOWN** | Unknown | **RESOLVER_LIGHT** | Inspect current search/apply network and fingerprint structured datasource |
| 165 | Dataminr | First-party careers current with live open-roles entry points and engineering-role surfaces. No current hosted ATS/backend proof captured in this audit. | Backend unknown | **FIRST_PARTY_VERIFIED / BACKEND_UNKNOWN** | Unknown | **RESOLVER_LIGHT** | Follow View Open Roles + inspect datasource/network before assigning ATS |
| 166 | Teleport | First-party careers page current and exposes an Explore Careers path; no current hosted ATS proof strong enough in this audit. | Backend unknown | **FIRST_PARTY_VERIFIED / BACKEND_UNKNOWN** | Unknown | **RESOLVER_LIGHT** | Follow current Explore Careers destination and fingerprint datasource |

## Audit-v2 corrections / closures — Batch 16

### Arctic Wolf — Workday now automation-grade

This is stronger than a third-party ATS directory claim:

1. the current Arctic Wolf first-party hiring FAQ says applicants apply to jobs individually **within Workday**;
2. current 2026 job requisitions resolve to `arcticwolf.wd1.myworkdayjobs.com/en-US/External/...`;
3. requisition IDs such as `R26_825` are exposed by Workday.

Therefore Arctic Wolf can bypass generic portal resolution and go directly to the existing Workday adapter.

### BeyondTrust — Greenhouse current board verified

A live current board exists at:

```text
https://job-boards.greenhouse.io/beyondtrust
```

It exposes ~64–65 current openings and matches BeyondTrust's current first-party careers content. This is sufficient for `OPERATIONAL_PLATFORM_VERIFIED`; catalog parity still belongs to the controlled API probe rather than the census.

### Cyberhaven — Ashby current board verified

The current board root is reachable today at:

```text
https://jobs.ashbyhq.com/cyberhaven
```

and current 2026 roles use Ashby UUID job URLs. Promote Cyberhaven to `FAST_PATH` with the existing Ashby adapter.

### Aiven — important evidence-grade example

Aiven's first-party careers page currently says legitimate recruiting communications may come from `@greenhouse.io` and `@eu.greenhouse.io`. This is strong evidence that Greenhouse is part of the current recruiting stack, but **does not by itself identify the public board token or prove catalog completeness**.

Therefore:

```text
current platform evidence = strong
board/API identity          = unresolved
FAST_PATH                   = not yet automatic
```

One cheap apply-link/network fingerprint should be enough to close it.

### Illumio — stale structured evidence must not be treated as current proof

Illumio has strong Greenhouse history and hosted application evidence, but the surfaced board snapshot in this audit is stale while the first-party careers site is current. Do not promote based only on old Greenhouse pages. A fresh first-party apply-link or direct API hit is required.

---

## Audit-v2 frequency table — conservative minimum after 166 employers

Only rows with explicit v2 evidence are counted as confirmed; `PROBABLE`, stale, and backend-unknown rows are excluded from confirmed-family counts.

| Operational family | Audit-v2 confirmed minimum | Existing adapter | Implication |
|---|---:|---:|---|
| Greenhouse | **36+** | Yes | Dominant family; direct board-token/API verification should be fully automated |
| Ashby | **21+** | Yes | Strongest startup/AI/security fast path |
| Workday | **8+** | Yes | Enterprise/security/defense fast path |
| Oracle Recruiting Cloud | **3+** | Yes | Existing adapter already valuable |
| Lever | **2+** | Yes | Existing adapter sufficient |
| SmartRecruiters | **2+** | Yes | Existing adapter sufficient |
| Avature | **1+** | Yes | Existing adapter useful |
| Eightfold ecosystem | **1+ strong + candidates** | No dedicated confirmed adapter | Reusable adapter candidate |
| Talent Gateway / BrassRing | **1+ strong + candidates** | No | Reusable adapter candidate |
| Taleo | candidate(s) | No | Build only if repeated current use survives audit |
| Custom / backend unresolved | **18+** | N/A | Actual resolver / fingerprint queue |
| Google custom RPC | 1 | Yes in V24 | Example of custom discovery converted to deterministic adapter |

### Current verified-family concentration

At least:

```text
Greenhouse + Ashby + Workday
= 36 + 21 + 8
= 65 audit-v2 employers minimum
```

This remains a conservative lower bound because many legacy rows have not yet been re-promoted under v2.

---

## Next parallel work after 166

### Audit closure priority

1. Cloudflare — direct Boards API count vs first-party roles.
2. Okta — enumerate active Greenhouse board identities and scope.
3. SpaceX — resolve US/main catalog in addition to `spacexglobal`.
4. CoreWeave — establish first-party regional union parity.
5. Datadog — fresh direct board/API proof.
6. Databricks — fresh direct board/API proof.
7. N26 — derive current board token from first-party flow.
8. Dropbox — current direct board/API proof.
9. Aiven — derive board token from current application flow.
10. Illumio — fresh current Greenhouse/API proof rather than stale board snapshots.

### Unsupported-family priority

1. Eightfold — Ericsson + Vodafone protocol comparison.
2. Talent Gateway / BrassRing — UBS + IBM protocol comparison.
3. Taleo — only after at least two currently verified Tier-S users.

### Census continuation

Continue beyond 166 with high-value cyber/cloud/security infrastructure employers, while keeping the share of audit work at least as high as the share of new-company additions.

---

# Batch 17 — census + audit-v2 parallel continuation (2026-09-02)

## New employers 167–171

| # | Employer | Current career / operational evidence | ATS / backend | Audit-v2 status | Existing adapter | Queue | Next action |
|---:|---|---|---|---|---:|---|---|
| 167 | GuidePoint Security | Multiple current 2026 vacancies are live on `job-boards.greenhouse.io/guidepointsecurity/jobs/<id>`. Current job text explicitly states: “We use Greenhouse Software as our applicant tracking system.” | Greenhouse — board `guidepointsecurity` | **TECHNICALLY_VERIFIED** | Yes | **FAST_PATH** | Direct Boards API catalog probe + first-party parity |
| 168 | Dragos | Live board root today at `job-boards.greenhouse.io/dragos` exposes **53 current jobs**, including CTI, IR, malware, OT/ICS, product security and vulnerability roles. | Greenhouse — board `dragos` | **TECHNICALLY_VERIFIED / CURRENT_ROOT_CATALOG** | Yes | **FAST_PATH** | Boards API count + description coverage + first-party parity |
| 169 | Panther Labs | Live board root today at `job-boards.greenhouse.io/pantherlabs`; current board content explicitly describes Panther's AI SOC mission and lists active roles. | Greenhouse — board `pantherlabs` | **TECHNICALLY_VERIFIED / CURRENT_ROOT_CATALOG** | Yes | **FAST_PATH** | Boards API probe + first-party parity |
| 170 | Cribl | Greenhouse job evidence remains strong and older catalog snapshots expose dozens of jobs, but the Greenhouse root currently redirects to `cribl.io/careers`; the fetched first-party careers widget currently renders `Showing 0 of 0`, so neither source alone proves current complete catalog semantics. | Greenhouse participation strongly evidenced; authoritative current catalog unresolved | **FIRST_PARTY_VERIFIED / PLATFORM_STRONG / CATALOG_UNRESOLVED** | Yes if board remains authoritative | **FINGERPRINT_THEN_FAST_PATH** | Inspect current first-party `View open roles` datasource/network; only then select Greenhouse token or custom source |
| 171 | Veza | Recent Greenhouse catalog snapshots at `job-boards.greenhouse.io/veza/jobs/<id>` expose ~32 roles for Veza Technologies; however the board root currently returns 404 in direct fetch, so current platform/catalog continuity is not strong enough for automatic promotion. | Greenhouse historical/recent evidence; current root unavailable | **RECENT_PLATFORM_EVIDENCE / FRESH_PROBE_REQUIRED** | Yes if current token/source resolved | **FAST_PATH_CANDIDATE** | Follow current first-party careers/apply flow and re-resolve active board identity |

## Audit-v2 closures / corrections — Batch 17

### GuidePoint Security — unusually strong Greenhouse proof

GuidePoint is an example of the strongest possible platform evidence short of our own API probe. Current 2026 job pages are hosted by Greenhouse and the posting itself explicitly states that GuidePoint uses **Greenhouse Software as its applicant tracking system**. No generic resolver should ever be invoked for this employer before trying the existing Greenhouse adapter.

Operational source candidate:

```text
platform = Greenhouse
board_token = guidepointsecurity
```

Catalog completeness still belongs to the controlled Boards API probe.

### Dragos — current Greenhouse root catalog is alive

Direct current board root:

```text
https://job-boards.greenhouse.io/dragos
```

The live page exposes 53 jobs during this audit, including highly relevant P0 categories such as:

- Cyber Threat Intelligence;
- Incident Response;
- Malware Analysis;
- OT/ICS cybersecurity;
- Product Security Engineering;
- Vulnerability Analysis;
- Threat Detection / Hunting.

This is `OPERATIONAL_PLATFORM_VERIFIED` and suitable for immediate Greenhouse probe.

### Panther Labs — current Greenhouse root catalog is alive

Direct current board root:

```text
https://job-boards.greenhouse.io/pantherlabs
```

is live today and exposes active positions. Promote Panther from an unknown future resolver target to the existing Greenhouse fast path.

### Cribl — explicit downgrade despite strong historical Greenhouse evidence

Cribl demonstrates why a historical ATS signature cannot automatically drive production scanning:

```text
Greenhouse root today
→ redirects to first-party Cribl careers

first-party careers fetch
→ open-role component currently renders 0 / 0

older Greenhouse job/catalog snapshots
→ many jobs
```

This is inconsistent enough that **no source is yet catalog-authoritative**. The next action is a cheap network/datasource fingerprint on the first-party page, not an LLM resolver and not blind reuse of the old Greenhouse token.

### Veza — downgrade until fresh operational identity is proven

Recent indexed Greenhouse job pages strongly indicate Greenhouse usage, but direct board-root resolution currently fails. Keep the employer out of automatic fast-path execution until the current first-party apply flow identifies the active source.

---

## Audit follow-up — high-value unresolved cases

### N26

Current first-party job URLs still include `gh_jid` (for example `/careers/positions/<id>?gh_jid=<id>`), and N26's own current recruiting-tool role names Greenhouse among its People applications. This raises platform confidence further, but **does not reveal the active public board token/catalog identity**. Status remains `FINGERPRINT_THEN_FAST_PATH`, not catalog-verified.

### Datadog

Current first-party job pages continue to use `?gh_jid=<id>` and current recruiting material references Greenhouse internally. This is strong evidence that Greenhouse remains operational in the application flow. Still require direct board/API identity + count before `COMPLETE_CATALOG_VERIFIED`.

### Aiven

Current first-party careers explicitly recognizes `@greenhouse.io` / `@eu.greenhouse.io` as legitimate recruitment domains. Platform confidence is strong; exact public operational board identity remains the missing deterministic step.

### Wiz

A live `wizprivate` Greenhouse board exists but currently exposes only a tiny engineering subset in the observed snapshot, while older `wizinc` evidence exists. Therefore **do not equate one visible Wiz Greenhouse board with global Wiz catalog completeness**. Model Wiz as a potential multi-source / migrated-board case until first-party parity is proven.

---

## Audit-v2 frequency table — conservative minimum after 171 employers

Only explicitly v2-audited platform confirmations are counted. Stale/probable/current-but-unresolved platform evidence is excluded from the confirmed minimum.

| Operational family | Audit-v2 confirmed minimum | Existing adapter | Implication |
|---|---:|---:|---|
| Greenhouse | **39+** | Yes | Dominant family; board identity discovery + API parity should be automated |
| Ashby | **21+** | Yes | Strong startup/AI/security fast path |
| Workday | **8+** | Yes | Enterprise/security/defense fast path |
| Oracle Recruiting Cloud | **3+** | Yes | Existing adapter valuable |
| Lever | **2+** | Yes | Existing adapter sufficient |
| SmartRecruiters | **2+** | Yes | Existing adapter sufficient |
| Avature | **1+** | Yes | Existing adapter useful |
| Eightfold ecosystem | **1+ strong + candidates** | No dedicated confirmed adapter | Reusable-adapter candidate |
| Talent Gateway / BrassRing | **1+ strong + candidates** | No | Reusable-adapter candidate |
| Taleo | candidate(s) | No | Build only if repeated current usage survives audit |
| Google custom RPC | 1 | Yes in V24 | Custom discovery already converted to deterministic adapter |
| Custom / backend unresolved | **18+** | N/A | Actual resolver/fingerprint queue |

### Verified-family concentration

```text
Greenhouse + Ashby + Workday
>= 39 + 21 + 8
>= 68 audit-v2 employers
```

This remains a conservative lower bound because legacy mappings are promoted only after fresh v2 evidence.

---

## Updated next parallel work after 171

### Priority A — cheap closures that can unlock existing adapters

1. Cloudflare — direct Boards API count vs first-party catalog.
2. Okta — enumerate active Greenhouse board identities / regional scope.
3. SpaceX — identify main/US operational source in addition to `spacexglobal`.
4. CoreWeave — regional first-party union vs Greenhouse catalog.
5. Datadog — derive current board identity and direct API count.
6. Databricks — derive current board identity and direct API count.
7. N26 — derive public/current Greenhouse board identity from application flow.
8. Aiven — derive current board identity from first-party apply flow.
9. Illumio — fresh first-party apply / API proof.
10. Cribl — inspect current first-party jobs datasource because the historical root redirects.

### Priority B — unsupported reusable families

1. **Eightfold:** compare Ericsson + Vodafone request/response contracts.
2. **Talent Gateway / BrassRing:** compare UBS + IBM and determine whether one adapter can cover both.
3. **Taleo:** only invest after a second currently verified valuable employer appears.

### Priority C — census continuation

Continue toward ~180, but do not let new-company additions crowd out audit closure. At this stage, converting `PROBABLE` into automation-grade sources has higher marginal value than adding low-priority employers.

---

# Batch 18 — census + audit-v2 parallel continuation (2026-09-02)

## New employers 172–179

| # | Employer | Current career / operational evidence | ATS / backend | Audit-v2 status | Existing adapter | Queue | Next action |
|---:|---|---|---|---|---:|---|---|
| 172 | Trend Micro / TrendAI | Current 2026 vacancies are directly hosted on `trendmicro.wd3.myworkdayjobs.com/External`, with live requisition IDs such as `R0009988`, `R0010158`, `R0010137`, and current posting dates. | Workday — tenant `trendmicro`, site `External` | **TECHNICALLY_VERIFIED** | Yes | **FAST_PATH** | Direct Workday catalog probe + first-party parity |
| 173 | Sekoia | Current first-party career site `careers.sekoia.com` explicitly exposes `Vendors Teamtailor`, `images.teamtailor-cdn.com`, employee/candidate login conventions, and `Career site by Teamtailor`. Current jobs are listed on that same surface. | Teamtailor | **FIRST_PARTY_AND_PLATFORM_VERIFIED** | No dedicated adapter currently | **ADAPTER_NEEDED** | Study Teamtailor public/anonymous jobs datasource once; build reusable adapter if structured endpoint is stable |
| 174 | WithSecure | Current first-party `withsecure.com/.../careers/open-positions` exposes an active filterable job catalog with locations/categories and current roles. No current ATS/backend identity was proven in this audit. | First-party custom surface; backend unresolved | **FIRST_PARTY_VERIFIED / BACKEND_UNKNOWN** | Unknown | **RESOLVER_LIGHT** | Inspect job-detail/apply links + network datasource before any ATS claim |
| 175 | ESET | Current first-party ESET careers pages expose worldwide/current opportunities and location-specific open-position surfaces. No single current global ATS/backend was proven; regional surfaces may differ. | Multi-surface first-party; backend unresolved | **FIRST_PARTY_VERIFIED / GLOBAL_BACKEND_UNKNOWN** | Unknown | **RESOLVER_LIGHT / MULTI_SOURCE_CANDIDATE** | Trace HQ/global job links plus 2–3 regional apply flows; model regional sources if necessary |
| 176 | Splunk | Current first-party Splunk careers search exposes filters, teams (including Splunk Global Security), job type, location and load-more behavior. Backend remains unproven in this audit, and Cisco ownership means historical ATS assumptions are especially unsafe. | First-party custom / backend unresolved | **FIRST_PARTY_VERIFIED / BACKEND_UNKNOWN** | Unknown | **RESOLVER_LIGHT** | Inspect search XHR/network and determine whether Cisco/Splunk use a shared or separate datasource |
| 177 | Glean | Live current board root `job-boards.greenhouse.io/gleanwork` exposes roughly 110+ active roles, including security/governance engineering and product roles. | Greenhouse — board `gleanwork` | **TECHNICALLY_VERIFIED / CURRENT_ROOT_CATALOG** | Yes | **FAST_PATH** | Boards API probe + first-party parity |
| 178 | Anyscale | Current Lever legacy page explicitly says the careers page moved to `jobs.ashbyhq.com/anyscale`, providing direct platform-transition evidence. | Ashby — board/org `anyscale` | **TECHNICALLY_VERIFIED / MIGRATION_CONFIRMED** | Yes | **FAST_PATH** | Ashby catalog probe + verify old Lever contains no active unique jobs |
| 179 | Pure Storage / Everpure | Current Greenhouse board root `job-boards.greenhouse.io/purestorage` is live and exposes ~300+ jobs. Current branding on the board is Everpure, so corporate/brand identity must be represented explicitly rather than inferred from board token alone. | Greenhouse — board `purestorage` | **TECHNICALLY_VERIFIED / BRAND_TRANSITION_NOTE** | Yes | **FAST_PATH_WITH_IDENTITY_CHECK** | Boards API probe; map Pure Storage/Everpure corporate identity before DB ingestion |

## Audit-v2 closures / findings — Batch 18

### Trend Micro — Workday is current, not historical

Current vacancies resolve directly to:

```text
https://trendmicro.wd3.myworkdayjobs.com/External/job/..._R00xxxx
```

with live 2026 requisitions and posting dates. This is sufficient to bypass generic discovery and invoke the existing Workday adapter first.

### Sekoia — Teamtailor is directly proven by first-party HTML

This is a strong unsupported-platform finding. The current Sekoia career site itself exposes:

```text
Vendors Teamtailor
images.teamtailor-cdn.com
Career site by Teamtailor
```

Therefore:

```text
Sekoia
→ Teamtailor
→ no resolver needed to identify platform
→ reusable Teamtailor adapter candidate
```

Do not use an AI resolver for Sekoia before trying to reverse the standard Teamtailor jobs datasource.

### Glean — current Greenhouse root is alive

Direct root:

```text
https://job-boards.greenhouse.io/gleanwork
```

is current and exposes roughly 110+ jobs during this audit, including security-oriented roles. Platform selection is automation-grade; catalog parity remains a controlled-probe task.

### Anyscale — useful migration pattern

The old Lever page is not merely stale: it explicitly announces that Anyscale moved its careers page to Ashby. This creates a valuable deterministic migration signature:

```text
old ATS board
→ explicit migration notice
→ new ATS board
```

The future fingerprint layer should be allowed to follow such explicit provider-to-provider migration signals and retire the old source only after verifying no unique active jobs remain.

### Pure Storage / Everpure — platform verified, corporate identity needs care

The board token remains `purestorage`, while the current board presents the employer as **Everpure**. The scanner must not silently equate board-token naming with canonical employer naming. This reinforces the existing design principle:

```text
operational source identity
!=
canonical corporate identity
```

The source can be scanned immediately, but corporate-cluster mapping must remain explicit.

### Datadog and Databricks — platform evidence remains strong, fresh completeness proof still pending

Current search results continue to surface Greenhouse catalog structures for both, but the crawl snapshots available in this audit are not fresh enough to upgrade them to `COMPLETE_CATALOG_VERIFIED` today. Keep the existing platform confidence, but still require a direct Boards API request before production auto-promotion.

---

## Audit-v2 frequency table — conservative minimum after 179 employers

Only explicit v2 platform confirmations are counted. `PROBABLE`, stale, and backend-unknown rows remain excluded.

| Operational family | Audit-v2 confirmed minimum | Existing adapter | Implication |
|---|---:|---:|---|
| Greenhouse | **41+** | Yes | Dominant family; board-token/API verification should be deterministic |
| Ashby | **22+** | Yes | Major startup/AI fast path |
| Workday | **9+** | Yes | Enterprise/security fast path |
| Oracle Recruiting Cloud | **3+** | Yes | Existing adapter valuable |
| Lever | **2+** | Yes | Existing adapter sufficient |
| SmartRecruiters | **2+** | Yes | Existing adapter sufficient |
| Avature | **1+** | Yes | Existing adapter useful |
| Teamtailor | **1 directly verified + likely future repeats** | **No** | New reusable-adapter candidate |
| Eightfold ecosystem | **1+ strong + candidates** | No dedicated adapter | Reusable-adapter candidate |
| Talent Gateway / BrassRing | **1+ strong + candidates** | No | Reusable-adapter candidate |
| Taleo | candidate(s) | No | Build only after repeated current use |
| Google custom RPC | 1 | Yes in V24 | Custom discovery already converted to deterministic adapter |
| Custom / backend unresolved | **21+** | N/A | True fingerprint/resolver queue |

### Verified-family concentration

```text
Greenhouse + Ashby + Workday
>= 41 + 22 + 9
>= 72 audit-v2 employers
```

This remains deliberately conservative.

### Unsupported-platform ROI signal

We now have at least three concrete reusable-platform targets:

```text
Teamtailor
Eightfold
Talent Gateway / BrassRing
```

Priority should not be decided by novelty. It should be decided by:

```text
(number of valuable employers using platform)
×
(expected catalog completeness)
÷
implementation / maintenance cost
```

Teamtailor is now proven first-party through Sekoia and is likely to be relatively easy to fingerprint compared with fully proprietary portals, so it deserves a cheap protocol investigation before sending Sekoia to a generic resolver.

---

## Updated next parallel work after 179

### Priority A — audit closures using existing adapters

1. Cloudflare — direct Greenhouse Boards API count vs first-party.
2. Okta — resolve complete current Greenhouse board set / region scope.
3. SpaceX — resolve main/US source plus `spacexglobal` union.
4. CoreWeave — prove Greenhouse vs regional first-party union parity.
5. Datadog — direct current Boards API count.
6. Databricks — direct current Boards API count.
7. N26 — derive active Greenhouse board identity.
8. Aiven — derive board token from first-party apply path.
9. Illumio — fresh current board/API proof.
10. Cribl — current first-party datasource fingerprint.

### Priority B — reusable unsupported-platform studies

1. Teamtailor — Sekoia as first clean fixture; discover anonymous catalog/detail protocol.
2. Eightfold — Ericsson + Vodafone protocol comparison.
3. Talent Gateway / BrassRing — UBS + IBM protocol comparison.
4. Taleo — only if another valuable current user survives audit.

### Priority C — census continuation

Continue toward ~190–200, but audit closure now has higher marginal value than raw additions. New entries should favor high-value cyber, cloud, AI infrastructure, finance, aerospace and major European employers rather than filler companies.


# Batch 19 — census + audit-v2 parallel continuation (2026-09-02)

## New employers 180–188

| # | Employer | Current career / operational evidence | ATS / backend | Audit-v2 status | Existing adapter | Queue | Next action |
|---:|---|---|---|---|---:|---|---|
| 180 | ReliaQuest | Current 2026 requisitions are directly live on `reliaquest.wd5.myworkdayjobs.com/ReliaQuest_Careers`, including early-career/security roles such as GreyMatter Specialist and Associate Software Engineer with current requisition IDs. | Workday — tenant `reliaquest`, site `ReliaQuest_Careers` | **TECHNICALLY_VERIFIED** | Yes | **FAST_PATH** | Direct Workday catalog probe + first-party parity |
| 181 | Coalition | Current first-party Coalition careers pages explicitly state: “We use an applicant tracking system called Greenhouse”, while current regional boards such as `de-coalition` are live on Greenhouse. | Greenhouse — multi/regional board structure | **FIRST_PARTY_AND_PLATFORM_VERIFIED / MULTI_SOURCE_NOTE** | Yes | **FAST_PATH_WITH_SOURCE_ENUMERATION** | Enumerate all current Coalition board identities, union/dedupe, compare to first-party jobs |
| 182 | AlphaSense | Current root `job-boards.greenhouse.io/alphasense` is live today with ~228–230 active jobs and current security/IAM roles. | Greenhouse — board `alphasense` | **TECHNICALLY_VERIFIED / CURRENT_ROOT_CATALOG** | Yes | **FAST_PATH** | Boards API probe + first-party parity |
| 183 | Google DeepMind | Current root `job-boards.greenhouse.io/deepmind` is live today with active Frontier AI / Gemini / safety roles. DeepMind must remain a distinct operational source from the main Google Careers RPC unless parity is proven. | Greenhouse — board `deepmind` | **TECHNICALLY_VERIFIED / DISTINCT_GOOGLE_SOURCE** | Yes | **FAST_PATH_WITH_CLUSTER_UNION** | Probe Greenhouse board and union with Google corporate cluster without deduping by description |
| 184 | Endor Labs | Current root `job-boards.greenhouse.io/endorlabs` is live today with ~28–29 jobs, including Product Security, Vulnerability Management, Security Research and IT roles. | Greenhouse — board `endorlabs` | **TECHNICALLY_VERIFIED / CURRENT_ROOT_CATALOG** | Yes | **FAST_PATH** | Boards API probe + first-party parity |
| 185 | Horizon3.ai | Current job detail pages are directly hosted on `jobs.ashbyhq.com/horizon3ai/<uuid>` for live 2026 roles, including EMEA/Italy-facing positions and Security/IT roles. | Ashby — org `horizon3ai` | **TECHNICALLY_VERIFIED** | Yes | **FAST_PATH** | Ashby catalog probe + first-party parity |
| 186 | Fable Security | Current job detail pages are directly live on `jobs.ashbyhq.com/fable/<uuid>`, including Head of IT & Information Security and engineering roles. | Ashby — org `fable` | **TECHNICALLY_VERIFIED** | Yes | **FAST_PATH** | Ashby catalog probe + first-party parity |
| 187 | Artemis Security | Multiple current 2026 roles are directly live on `jobs.ashbyhq.com/artemis/<uuid>`, including Security Analyst, Security Engineer and internal security roles. | Ashby — org `artemis` | **TECHNICALLY_VERIFIED** | Yes | **FAST_PATH** | Ashby catalog probe + first-party parity |
| 188 | N26 | Current first-party application flow has been technically observed embedding `job-boards.greenhouse.io/embed/job_app?for=n26&token=...`; current first-party job URLs also retain Greenhouse-style `gh_jid`. This proves Greenhouse is operational, but root-catalog completeness still requires a direct API probe. | Greenhouse — board identity `n26` technically exposed by current apply flow | **TECHNICALLY_VERIFIED_PLATFORM / CATALOG_PARITY_PENDING** | Yes | **FAST_PATH_CANDIDATE** | Direct Boards API `n26` probe, compare count/IDs to first-party catalog, then promote or split sources |

## Audit-v2 findings — Batch 19

### ReliaQuest — Workday can bypass resolver entirely

Current requisitions resolve directly to:

```text
https://reliaquest.wd5.myworkdayjobs.com/ReliaQuest_Careers/..._Rxxxxx
```

with current posting dates and stable requisition IDs. This is an immediate existing-adapter fast path.

### Coalition — first-party confirmation beats inferred ATS mapping

Coalition's current careers pages explicitly say they use **Greenhouse** as their ATS. At least one regional Greenhouse board (`de-coalition`) is currently live. Because Coalition operates across multiple regions, the correct production model is:

```text
Coalition corporate cluster
→ operational_sources[]
→ enumerate regional/current Greenhouse boards
→ union + stable-ID dedupe
```

Do not assume `de-coalition` alone is the global catalog.

### AlphaSense — current root catalog is directly observable

`job-boards.greenhouse.io/alphasense` is live today and exposes roughly 228–230 current openings. This is stronger than a single `gh_jid` clue: platform and root catalog are both current.

### Google DeepMind — one corporate cluster can legitimately have heterogeneous platforms

DeepMind currently has its own live Greenhouse board while the main Google Careers catalog is handled by the Google custom RPC implemented in V24. Therefore the corporate model must support:

```text
Google / Alphabet cluster
├── Google Careers RPC
└── DeepMind Greenhouse
```

This is another concrete reason not to force one ATS/backend per company or corporate cluster.

### N26 — promoted from inference to technically observed Greenhouse flow

A fresh technical scan of the current N26 apply flow shows the first-party page embedding:

```text
job-boards.greenhouse.io/embed/job_app?for=n26&token=<job_id>
```

This is enough to mark Greenhouse as operational today. It is **not yet enough** to claim the `n26` root board is the complete global catalog; that remains a one-request Boards API + parity check.

---

## Audit-v2 frequency table — conservative minimum after 188 employers

Only explicit v2 confirmations are counted; `PROBABLE` and backend-unknown rows remain excluded.

| Operational family | Audit-v2 confirmed minimum | Existing adapter | Implication |
|---|---:|---:|---|
| Greenhouse | **45+** | Yes | Dominant family; source enumeration/parity is now the main issue, not parsing |
| Ashby | **25+** | Yes | Major startup/AI/security fast path |
| Workday | **10+** | Yes | Strong enterprise/security fast path |
| Oracle Recruiting Cloud | **3+** | Yes | Existing adapter valuable |
| Lever | **2+** | Yes | Existing adapter sufficient |
| SmartRecruiters | **2+** | Yes | Existing adapter sufficient |
| Avature | **1+** | Yes | Existing adapter useful |
| Teamtailor | **1 directly verified + likely repeats** | No | Reusable-adapter candidate |
| Eightfold ecosystem | **1+ strong + candidates** | No dedicated adapter | Reusable-adapter candidate |
| Talent Gateway / BrassRing | **1+ strong + candidates** | No | Reusable-adapter candidate |
| Google custom RPC | 1 | Yes in V24 | Deterministic custom adapter already built |
| Custom / backend unresolved | **21+** | N/A | Actual resolver/fingerprint queue |

### Verified-family concentration

```text
Greenhouse + Ashby + Workday
>= 45 + 25 + 10
>= 80 audit-v2 employers
```

This is a conservative minimum and now spans 188 censused employers.

### Architectural signal after 188

The dominant remaining problem is increasingly **source identity and completeness**, not ATS parser availability. Examples now include:

- one employer with multiple regional Greenhouse boards;
- one corporate cluster with heterogeneous platforms (Google RPC + DeepMind Greenhouse);
- first-party vanity pages embedding a known ATS only for application;
- migrations where historical ATS roots redirect while detail/apply paths remain live.

Therefore the automation layer should fingerprint and validate `operational_sources[]` rather than assign a single `ats_family` to an employer and stop.

---

## Updated next parallel work after 188

### Priority A — close high-value existing-adapter cases

1. N26 — direct Greenhouse Boards API parity check.
2. Cloudflare — direct root API count vs first-party catalog.
3. Okta — enumerate all current board identities / regional scope.
4. SpaceX — resolve US/main source plus `spacexglobal`.
5. CoreWeave — regional first-party union vs Greenhouse.
6. Datadog — current board/API count.
7. Databricks — current board/API count.
8. Aiven — derive current board token from first-party apply flow.
9. Illumio — fresh API/root proof.
10. Coalition — enumerate regional Greenhouse sources.

### Priority B — unsupported reusable platforms

1. Teamtailor — Sekoia fixture.
2. Eightfold — Ericsson + Vodafone comparison.
3. Talent Gateway / BrassRing — UBS + IBM comparison.
4. Taleo — only if repeated current usage survives audit.

### Priority C — census continuation

Continue toward the 200-employer initial freeze, but avoid filler: the final 12 should be high-value cyber, AI infrastructure, finance, aerospace/defense, automotive or major European employers.

---

# Batch 17 — Freeze to 200 CORE + audit-v2 continuation (2026-09-02)

This batch deliberately closes the **initial 200-employer census**. Selection for 189–200 favors high-value cybersecurity / defense / identity employers rather than easy ATS wins. Audit-v2 rules remain in force: an operational platform may be verified without claiming complete global catalog parity.

| Priority | Employer | Current careers / operational surface | Operational ATS / backend | Audit-v2 confidence | Existing adapter | Path | Next action |
|---:|---|---|---|---|---:|---|---|
| 189 | Tanium | First-party Tanium careers links to a live current catalog at `job-boards.greenhouse.io/tanium`; the board currently exposes ~40+ jobs and explicit `IT Security` categories. | Greenhouse — board `tanium` | **TECHNICALLY_VERIFIED / CURRENT_ROOT_CATALOG** | Yes | **FAST_PATH** | Boards API probe, description coverage, first-party parity |
| 190 | Shield AI | First-party `shield.ai/careers` exposes open roles; the current complete role surface is live at `jobs.lever.co/shieldai`, including a `Cybersecurity` team/category and current requisitions. | Lever — site `shieldai` | **FIRST_PARTY_AND_PLATFORM_VERIFIED / CURRENT_ROOT_CATALOG** | Yes | **FAST_PATH** | Lever catalog probe + compare with first-party Open Roles; treat Aechelon as a distinct subsidiary source |
| 191 | Helsing | First-party `helsing.ai/careers` and current job URLs are live; current ecosystem evidence points to Greenhouse, but this audit did not get a clean root-board response sufficient to claim catalog authority. | Greenhouse strongly indicated; first-party job surface current | **FIRST_PARTY_VERIFIED / PLATFORM_STRONG / CATALOG_PROBE_REQUIRED** | Yes if Greenhouse confirmed | **FINGERPRINT_THEN_FAST_PATH** | Resolve current board/token from first-party apply flow and run Boards API parity test |
| 192 | SailPoint | Current Workday career endpoint `sailpoint.wd1.myworkdayjobs.com/SailPoint/jobs` is live today; historical/current technical traces consistently identify the same tenant/site. | Workday — tenant `sailpoint`, site `SailPoint` | **TECHNICALLY_VERIFIED_PLATFORM** | Yes | **FAST_PATH** | Workday structured catalog probe + first-party parity |
| 193 | Abnormal Security | Current first-party job URLs use `careers.abnormalsecurity.com/jobs/<id>` and Greenhouse-style `gh_jid`; recent current postings resolve through the Greenhouse family. | Greenhouse — operational family strongly evidenced; board identity `abnormalsecurity` | **FIRST_PARTY_VERIFIED / PLATFORM_STRONG / CATALOG_PARITY_PENDING** | Yes | **FAST_PATH_CANDIDATE** | Direct Boards API/token probe and compare IDs/count against first-party catalog |
| 194 | Saronic Technologies | Multiple current jobs are directly live on `jobs.ashbyhq.com/saronic/<uuid>`, including AppSec, Security Operations and AI Platform Security roles. | Ashby — org `saronic` | **TECHNICALLY_VERIFIED** | Yes | **FAST_PATH** | Ashby catalog probe + first-party parity |
| 195 | CHAOS Industries | Live current root `job-boards.greenhouse.io/chaosindustries` exposes ~140+ active roles today. | Greenhouse — board `chaosindustries` | **TECHNICALLY_VERIFIED / CURRENT_ROOT_CATALOG** | Yes | **FAST_PATH** | Boards API count + first-party parity |
| 196 | Sophos | Current Sophos careers surface is first-party and active, but this audit did not establish a current supported ATS/backend with enough confidence for automation. | Backend unresolved | **FIRST_PARTY_VERIFIED / BACKEND_UNKNOWN** | Unknown | **RESOLVER_LIGHT** | Follow current search/apply flow, inspect XHR/redirect chain, then fingerprint before any adapter claim |
| 197 | Imperva | `careers.imperva.com` currently redirects to Imperva's first-party company/careers surface; anti-automation/interstitial behavior prevents treating a guessed historical ATS as current ground truth. | Backend unresolved | **FIRST_PARTY_VERIFIED / BACKEND_UNKNOWN** | Unknown | **RESOLVER_LIGHT** | Inspect first-party open-role links/network in a browser; prefer structured datasource if exposed |
| 198 | NETSCOUT | Current NETSCOUT careers surface exists but the backend/platform was not directly proven in this audit. | Backend unresolved | **FIRST_PARTY_VERIFIED / BACKEND_UNKNOWN** | Unknown | **RESOLVER_LIGHT** | Follow live job-search/apply flow and fingerprint operational source |
| 199 | Acronis | Current Acronis careers surface exists, but this audit did not obtain enough direct evidence to assign a supported ATS family safely. | Backend unresolved | **FIRST_PARTY_VERIFIED / BACKEND_UNKNOWN** | Unknown | **RESOLVER_LIGHT** | Inspect current catalog requests/apply redirects and determine structured backend |
| 200 | Claroty | Claroty remains a very high-value OT/ICS security target. Greenhouse usage is strongly suggested by current ecosystem traces, but a clean current first-party-to-board/catalog proof was not captured in this audit. | Greenhouse candidate / backend not yet automation-grade | **FIRST_PARTY_VERIFIED / PLATFORM_PROBABLE / FRESH_PROBE_REQUIRED** | Yes if Greenhouse confirmed | **FINGERPRINT_THEN_FAST_PATH** | Resolve current apply target/board identity and test Boards API before promotion |

## Audit-v2 evidence highlights — Batch 17

### Tanium
- Live current Greenhouse root: `https://job-boards.greenhouse.io/tanium`.
- Current board exposes roughly 40–50 jobs and explicit `IT Security` groupings.
- First-party Tanium careers presents the same open-opportunity model.

### Shield AI
- First-party: `https://shield.ai/careers/`.
- Current operational catalog: `https://jobs.lever.co/shieldai`.
- The current Lever catalog contains a dedicated `Enterprise Operations Division -> Cybersecurity` grouping and current requisitions.
- Shield AI-owned Aechelon uses a separate Greenhouse source; therefore Shield AI is another proof that a corporate group can require `operational_sources[]`.

### SailPoint
- Current Workday endpoint observed live: `https://sailpoint.wd1.myworkdayjobs.com/SailPoint/jobs`.
- Treat tenant/site as technically verified, but catalog completeness still belongs to the controlled Workday probe stage.

### Saronic Technologies
- Multiple current 2026 jobs live directly under `jobs.ashbyhq.com/saronic/<uuid>`.
- Current security examples include Application Security, Security Operations and AI Platform Security.

### CHAOS Industries
- Current Greenhouse root `chaosindustries` is live and exposes ~140+ jobs.
- This is suitable for direct structured Greenhouse probing without resolver reasoning.

## Initial 200-CORE census: FROZEN

The initial ATS census now contains **200 employers**. `FROZEN` does **not** mean every mapping is verified. It means the employer selection/census phase has enough breadth to stop expanding by default and move effort toward verification + automated probing.

From this point, new employers should be added only when one of these is true:

1. materially higher career value than an existing CORE employer;
2. fills a missing geography/sector that matters to the project;
3. is discovered as a necessary subsidiary/operational source of an existing corporate cluster.

Otherwise the priority is now **audit and execution**, not further list growth.

## Conservative audit-v2 family floor after Batch 17

These are deliberately minimum counts, not inferred totals. Only explicit audit-v2 mappings are counted.

| Operational family | Minimum audit-v2 employers | Existing adapter? | Strategic meaning |
|---|---:|---:|---|
| Greenhouse | **47+** | Yes | Highest-volume fast path; automate tenant/token probes in bulk |
| Ashby | **26+** | Yes | Second-highest fast path; straightforward structured catalog probing |
| Workday | **11+** | Yes | High-value enterprise/defense/finance coverage |
| Lever | **3+** | Yes | Low count but already solved; Shield AI joins Palantir/Spotify-class usage |
| Oracle Recruiting Cloud | **3+** | Yes | Enterprise fast path already supported |
| SmartRecruiters | **2+** | Yes | Existing adapter; continue direct fingerprinting |
| Avature | **1+** | Yes | Existing adapter |
| Teamtailor | **1+** | No | Reusable unsupported family; candidate adapter after probe |
| Talent Gateway / BrassRing | **1+** | No | Repeated/strategic unsupported family; strong adapter candidate |
| Eightfold ecosystem | **1+** | No | Repeated candidate; fingerprint current Microsoft/Vodafone/Ericsson-like surfaces |
| Custom / backend unresolved | **20+** | N/A | Only this residual set should consume resolver-agent reasoning |
| Google custom RPC | **1** | V24 | Already implemented separately |

## Execution pivot after the 200-CORE freeze

The project should now stop treating census growth as the main workstream. The next operating loop is:

```text
200 CORE ledger
      ↓
audit-v2 / cheap fingerprint
      ↓
┌───────────────────────────────┐
│ existing adapter confirmed?   │
└──────────────┬────────────────┘
               │ YES
               ↓
      AUTOMATED CONTROLLED PROBE
      catalog / IDs / descriptions
      dedup / parity / completeness
               │
               ↓
         VERIFIED SOURCE

NO
↓
repeated known platform?
├─ YES → build one reusable adapter
└─ NO  → resolver AI / browser discovery
```

### Immediate high-ROI queues

**Queue A — existing adapter, probe now**
- Greenhouse/Ashby/Workday/Lever rows already audit-v2 verified.
- Include multi-source enumeration before ingestion for corporate groups such as Google/DeepMind, Shield AI/Aechelon, Coalition and SpaceX.

**Queue B — one cheap fingerprint before fast path**
- Cloudflare, Okta, SpaceX, CoreWeave, Datadog, Databricks, N26, Aiven, Illumio, Abnormal Security, Helsing, Claroty.

**Queue C — reusable adapter research**
1. Talent Gateway / BrassRing
2. Eightfold
3. Teamtailor
4. Oracle Taleo if repeated by the audited unresolved set

**Queue D — resolver-light/custom**
- Microsoft, Amazon/AWS, Meta, Apple and the remaining first-party custom portals.

This is the point where automated probing has higher expected value than extending the census further.

# Batch 18 — Expansion beyond the 200-CORE freeze + audit-v2 continuation (2026-09-02)

The initial 200 selection remains frozen as the original CORE baseline, but mapping may continue as a controlled expansion. New rows after 200 are marked **CORE_EXTENSION** and must still satisfy the same audit-v2 evidence standard. This batch prioritizes AI infrastructure, cybersecurity/GRC and defense employers with high career value.

| Priority | Employer | Current careers / operational surface | Operational ATS / backend | Audit-v2 confidence | Existing adapter | Path | Next action |
|---:|---|---|---|---|---:|---|---|
| 201 | OneTrust | First-party careers currently shows 85 roles; live root `job-boards.greenhouse.io/onetrust` shows the same 85-job order of magnitude and current roles including Information Security Assurance. | Greenhouse — board `onetrust` | **FIRST_PARTY_AND_PLATFORM_VERIFIED / CURRENT_ROOT_CATALOG** | Yes | **FAST_PATH** | One-request Boards API count + ID parity against first-party 85-role catalog |
| 202 | SecurityScorecard | Live root `job-boards.greenhouse.io/securityscorecard` currently exposes 39 jobs including Threat Intelligence-related roles. | Greenhouse — board `securityscorecard` | **TECHNICALLY_VERIFIED / CURRENT_ROOT_CATALOG** | Yes | **FAST_PATH** | Boards API + first-party parity + description coverage |
| 203 | Lambda | Multiple current jobs are directly live at `jobs.ashbyhq.com/lambda/<uuid>` / `Lambda/<uuid>`, including IAM and AI infrastructure roles. | Ashby — org `lambda` | **TECHNICALLY_VERIFIED** | Yes | **FAST_PATH** | Ashby root/catalog probe + normalize case-insensitive org identity (`lambda`/`Lambda`) |
| 204 | Cerebras Systems | Multiple current jobs are directly live at `jobs.ashbyhq.com/cerebras/<uuid>`, with current software, SRE, datacenter and inference roles. | Ashby — org `cerebras` | **TECHNICALLY_VERIFIED** | Yes | **FAST_PATH** | Ashby catalog probe + first-party parity |
| 205 | Together AI | Live root `job-boards.greenhouse.io/togetherai` exposes ~58–64 current roles and the first-party Together AI careers surface links to current openings. | Greenhouse — board `togetherai` | **FIRST_PARTY_AND_PLATFORM_VERIFIED / CURRENT_ROOT_CATALOG** | Yes | **FAST_PATH** | Boards API count + first-party parity; retain catalog changes as normal churn, not mismatch |
| 206 | Crusoe | Current first-party careers is live; multiple current roles are directly hosted at `jobs.ashbyhq.com/Crusoe/<uuid>` / `crusoe/<uuid>`, including IT/Compliance/Security. | Ashby — org `Crusoe` | **FIRST_PARTY_AND_PLATFORM_VERIFIED** | Yes | **FAST_PATH** | Ashby catalog probe + first-party parity; canonicalize org casing |
| 207 | CACI International | Current operational search uses `searchcareers.caci.com/careers?...domain=caci.com`; current payload exposes Eightfold PCS config and links events to `app.eightfold.ai`; current job IDs use the Eightfold-style 13-digit identifiers. | **Eightfold** — domain `caci.com` | **TECHNICALLY_VERIFIED_PLATFORM** | No dedicated adapter | **ADAPTER_NEEDED / HIGH_ROI_FIXTURE** | Use CACI as a clean Eightfold fixture; identify anonymous search API, pagination, detail endpoint and stable ID contract |
| 208 | QinetiQ | Current `careers.qinetiq.com/viewalljobs/?locale=en_US` is live with 71 roles and classic RMK behavior (`View Profile`, locale, categories, 50-result pagination). | SuccessFactors Recruiting Marketing **high-confidence fingerprint** | **FIRST_PARTY_VERIFIED / PLATFORM_HIGH_CONFIDENCE / DIRECT_BACKEND_PROOF_PENDING** | Yes if RMK fingerprint confirmed | **FINGERPRINT_THEN_FAST_PATH** | Inspect page/network for explicit RMK/SAP signature and then use existing SuccessFactors adapter |
| 209 | Kratos Defense & Security Solutions | First-party open-roles page explicitly states recruiting communications come from `recruiting@pereless.com` and says this is their applicant tracking system channel. | **Pereless** | **FIRST_PARTY_VERIFIED_PLATFORM** | No | **ADAPTER_NEEDED_CANDIDATE** | Inspect Pereless public job catalog/search interface; build only if platform repeats across CORE/extension set |
| 210 | Leidos | First-party Leidos careers is live and its search currently exposes thousands of jobs, including dedicated Cybersecurity and Security Operations categories; backend vendor not yet proven here. | Backend unresolved / first-party structured career surface | **FIRST_PARTY_VERIFIED / BACKEND_UNKNOWN** | Unknown | **RESOLVER_LIGHT** | Inspect search XHR/embedded state; prefer structured endpoint over HTML and fingerprint vendor before coding |
| 211 | General Atomics | First-party `ga.com/careers` links to `ga-careers.com`; current catalog exposes 500+ US jobs and explicit Security job category, but vendor/backend is not yet directly proven. | Backend unresolved / custom first-party career surface | **FIRST_PARTY_VERIFIED / BACKEND_UNKNOWN** | Unknown | **RESOLVER_LIGHT** | Inspect `ga-careers.com` search requests and identify operational backend/API before any ATS assignment |
| 212 | Groq | Current first-party Groq careers uses `gh_jid=<id>` in current job URLs, strongly demonstrating Greenhouse involvement; current root board identity was not independently proven in this batch. | Greenhouse operational family strongly indicated | **FIRST_PARTY_VERIFIED / PLATFORM_STRONG / ROOT_CATALOG_PROBE_REQUIRED** | Yes if board token confirmed | **FINGERPRINT_THEN_FAST_PATH** | Derive current board token from apply flow/network and run Boards API parity test |

## Audit-v2 evidence highlights — Batch 18

### OneTrust — direct first-party/root parity signal

The current OneTrust first-party careers page exposes **85 roles** and the live Greenhouse root `onetrust` independently exposes **85 current jobs** at the same audit point. This is unusually strong evidence that the root board is not merely an application widget but the operational catalog. It should still receive the normal one-request API parity check before `COMPLETE_CATALOG_VERIFIED` is persisted.

### CACI — Eightfold moves from candidate family to repeated verified platform

CACI is a strong Eightfold fixture:

```text
searchcareers.caci.com/careers/job/<13-digit-id>?domain=caci.com
app.eightfold.ai/events/...
Eightfold PCS configuration in current career payload
```

This is materially stronger than inferring Eightfold from UI shape. Together with the Ericsson/Vodafone evidence already in the ledger, Eightfold now has enough strategic recurrence to justify dedicated adapter research rather than treating each instance as a one-off custom portal.

### QinetiQ — high-confidence SuccessFactors RMK fingerprint, but not promoted blindly

The current QinetiQ surface has the classic SAP SuccessFactors Recruiting Marketing structure:

```text
/viewalljobs/?locale=en_US
View Profile
category navigation
Results 1-50 of 71
```

That is enough for a cheap deterministic fingerprint candidate, but this ledger intentionally does **not** call it technically verified until an explicit SAP/RMK signature or backend request is captured.

### Kratos — new unsupported family: Pereless

Kratos first-party careers explicitly names `recruiting@pereless.com` as the applicant-tracking-system communication channel. This establishes Pereless as a current operational platform without relying on a directory or historical job post. It is not automatically worth a new adapter yet: first measure recurrence across the extended employer universe.

### Leidos / General Atomics — good resolver-light fixtures

Both have large, useful first-party catalogs already visible today. The remaining task is backend identification, not proving that jobs exist. These are ideal for the future cheap-fingerprint stage because a successful datasource discovery could turn thousands of pages/jobs into one reusable structured integration.

## Conservative audit-v2 family floor after 212 mapped employers

Only explicit audit-v2 confirmations are included in the minimums; strong-but-unproven platform candidates remain excluded.

| Operational family | Minimum audit-v2 employers | Existing adapter? | Strategic meaning |
|---|---:|---:|---|
| Greenhouse | **50+** | Yes | Dominant fast path; parity/source enumeration remains the main task |
| Ashby | **29+** | Yes | Major AI/startup/security fast path |
| Workday | **11+** | Yes | Enterprise/defense/finance fast path |
| Lever | **3+** | Yes | Solved family |
| Oracle Recruiting Cloud | **3+** | Yes | Solved enterprise family |
| SmartRecruiters | **2+** | Yes | Solved family |
| Avature | **1+** | Yes | Solved family |
| Eightfold | **2+ verified/strong repeated fixtures** | No dedicated adapter | **High-priority reusable adapter candidate** |
| Teamtailor | **1+** | No | Reusable adapter candidate |
| Talent Gateway / BrassRing | **1+** | No | Reusable adapter candidate |
| Pereless | **1 first-party verified platform** | No | Measure recurrence before adapter work |
| SuccessFactors RMK | existing supported family + QinetiQ candidate | Yes | Cheap fingerprint can convert more rows to fast path |
| Custom / backend unresolved | remains material | N/A | Resolver/fingerprint queue only |

### Verified-family concentration after extension

```text
Greenhouse + Ashby + Workday
>= 50 + 29 + 11
>= 90 audit-v2 employer mappings
```

The expansion beyond 200 therefore strengthens rather than weakens the original architecture: deterministic platform fingerprinting plus existing adapters should remain the default, while agentic portal resolution is reserved for the residual custom/backend-unknown set.

## Updated parallel audit queue after Batch 18

### Existing-adapter parity/fingerprint closures

1. Cloudflare — root Boards API count vs first-party.
2. Okta — current board identities and regional/entity scope.
3. SpaceX — US/main source + `spacexglobal` union.
4. CoreWeave — first-party regional surfaces vs Greenhouse union.
5. Datadog — fresh root/API count.
6. Databricks — fresh root/API count.
7. N26 — board `n26` Boards API vs first-party catalog.
8. Aiven — derive current Greenhouse board identity.
9. Illumio — fresh board/API proof.
10. Groq — derive board token from current `gh_jid` apply flow.
11. QinetiQ — capture explicit SuccessFactors RMK technical signature.

### Reusable unsupported platform research

1. **Eightfold — now elevated:** CACI + Ericsson + Vodafone family evidence.
2. Talent Gateway / BrassRing — UBS + IBM comparison.
3. Teamtailor — Sekoia fixture and recurrence census.
4. Pereless — Kratos fixture; adapter only if recurrence warrants it.
5. Taleo — retain only if current audited recurrence survives.


# Batch 19 — Defense + cloud security expansion and audit-v2 closures (2026-09-02)

This batch continues the controlled extension beyond the original 200-CORE freeze. It prioritizes high-value defense/government contractors and cybersecurity/cloud-security companies, while also closing several legacy `PROBABLE` mappings with current first-party evidence.

| Priority | Employer | Current careers / operational surface | Operational ATS / backend | Audit-v2 confidence | Existing adapter | Path | Next action |
|---:|---|---|---|---|---:|---|---|
| 213 | Booz Allen Hamilton | Booz Allen's current official application FAQ explicitly says candidates apply through Workday and links the candidate account to `bah.wd1.myworkdayjobs.com`. | **Workday** — tenant `bah`, host family `wd1.myworkdayjobs.com` | **FIRST_PARTY_VERIFIED_PLATFORM** | Yes | **FAST_PATH** | Resolve exact external site slug from live careers handoff, then controlled Workday catalog probe |
| 214 | General Dynamics Information Technology (GDIT) | Current first-party `gdit.com/careers` is live and exposes direct cyber/cloud/intelligence job search, but this audit did not yet prove the underlying ATS/backend. | Backend unresolved / first-party structured career surface | **FIRST_PARTY_VERIFIED / BACKEND_UNKNOWN** | Unknown | **RESOLVER_LIGHT** | Inspect search XHR/network/embedded state and fingerprint operational backend before coding |
| 215 | SAIC | Current `jobs.saic.com` is live with same-day 2026 postings, explicit Cyber/Cloud/DevSecOps career fields and stable job detail/search surfaces. The vendor/backend was not directly proven in this audit. | Backend unresolved / current first-party job platform | **FIRST_PARTY_VERIFIED / BACKEND_UNKNOWN** | Unknown | **RESOLVER_LIGHT** | Inspect search/detail requests and identify structured API/vendor; avoid HTML pagination if a feed exists |
| 216 | Cyera | Current first-party Cyera careers surface exposes live positions, filters, departments, remote regions and security roles directly on `cyera.com`; no supported ATS family was directly proven here. | Backend unresolved / first-party structured career component | **FIRST_PARTY_VERIFIED / BACKEND_UNKNOWN** | Unknown | **RESOLVER_LIGHT** | Inspect Webflow/app embed/network calls and derive underlying catalog source before any ATS assignment |
| 217 | Orca Security | Current first-party Orca Security careers page is live and renders departmental open positions directly; no current first-party ATS signature was proven in this audit. | Backend unresolved / first-party structured career surface | **FIRST_PARTY_VERIFIED / BACKEND_UNKNOWN** | Unknown | **RESOLVER_LIGHT** | Follow `Explore Open Positions` / apply flow, inspect network, and fingerprint the catalog source |
| 218 | Sysdig | Current first-party careers links to open positions; current operational jobs are directly live on `jobs.lever.co/sysdig`, including Italy roles, and the page explicitly renders `Jobs powered by Lever`. | **Lever** — org `sysdig` | **FIRST_PARTY_AND_PLATFORM_VERIFIED** | Yes | **FAST_PATH** | Lever catalog probe + first-party parity + description coverage |
| 219 | Veeam Software | Current first-party careers shows ~228 jobs; live Greenhouse root `job-boards.greenhouse.io/veeamsoftware` currently exposes **224 jobs**, including Product AppSec, DevSecOps and compliance roles. | **Greenhouse** — board `veeamsoftware` (jobs currently served from EU Greenhouse host) | **FIRST_PARTY_AND_PLATFORM_VERIFIED / CURRENT_ROOT_CATALOG** | Yes | **FAST_PATH** | One-request Boards API count/IDs + compare against first-party; treat small count drift as normal churn if IDs reconcile |
| 220 | Forter | Current first-party Forter careers/openings are live; live Greenhouse root `job-boards.greenhouse.io/forter` exposes **37 current jobs** and matches the active first-party opportunity surface. | **Greenhouse** — board `forter` | **FIRST_PARTY_AND_PLATFORM_VERIFIED / CURRENT_ROOT_CATALOG** | Yes | **FAST_PATH** | Boards API + first-party count/ID parity + descriptions |
| 221 | Checkmarx | Current first-party Checkmarx careers page renders a live structured position table with department/location/apply actions, including Application Security Research and AppSec roles; backend vendor was not directly proven. | Backend unresolved / first-party structured jobs component | **FIRST_PARTY_VERIFIED / BACKEND_UNKNOWN** | Unknown | **RESOLVER_LIGHT** | Inspect apply URL/network/data source; preserve first-party table as parity oracle, not production parser unless necessary |
| 222 | Trellix | Current `careers.trellix.com` exposes ~40 live jobs with Cyber Threat Hunter, Cleared Cyber Security Engineer, Threat Intelligence and reverse engineering roles; backend implementation is not yet proven as a supported ATS family. | Backend unresolved / first-party job platform | **FIRST_PARTY_VERIFIED / BACKEND_UNKNOWN** | Unknown | **RESOLVER_LIGHT** | Inspect search/load-more/detail network traffic and identify structured source; avoid assuming WordPress-like presentation is the system of record |

## Audit-v2 overrides — existing rows

These entries supersede older confidence labels for the same employers.

### Helsing (row 191) — Greenhouse operational family promoted

A current first-party job is directly live at:

```text
https://helsing.ai/jobs/4939402101?gh_jid=4939402101
```

The first-party page renders the job and the complete application form while retaining the Greenhouse-style `gh_jid`. This is sufficient to promote **platform involvement** from `PLATFORM_STRONG` to:

```text
FIRST_PARTY_VERIFIED / GREENHOUSE_OPERATIONAL_PLATFORM_VERIFIED
```

It is **not** sufficient to claim a complete root catalog. The next step remains deriving the current board identity/token and running a Boards API parity check against `helsing.ai/jobs`.

### Abnormal AI / Abnormal Security (row 193) — Greenhouse operational family promoted

Current first-party jobs are live at URLs such as:

```text
https://abnormal.ai/careers/jobs/7832743003?gh_jid=7832743003
```

The current first-party page exposes the complete vacancy and embedded application flow. Multiple current 2026 job IDs use the same Greenhouse-style numeric identity. This upgrades the platform state to:

```text
FIRST_PARTY_VERIFIED / GREENHOUSE_OPERATIONAL_PLATFORM_VERIFIED
```

Root board/catalog parity still requires a direct Boards API probe before `COMPLETE_CATALOG_VERIFIED`.

### Veeam — important correction to presentation-layer inference

The first-party `careers.veeam.com/search-jobs` UI has the visual/search morphology of a hosted career frontend, which could easily be misclassified from presentation alone. The live operational root proves the useful source is Greenhouse:

```text
job-boards.greenhouse.io/veeamsoftware
→ 224 current jobs
```

while the first-party search reports ~228 at the same audit window. This reinforces the project rule:

```text
presentation technology != preferred operational source
```

The system should select the complete, structured, low-request source when parity is demonstrated, even if the vanity frontend uses another presentation stack.

## Audit-v2 evidence highlights — Batch 19

### Booz Allen — unusually strong first-party Workday proof

Booz Allen's official candidate FAQ explicitly says:

```text
view openings and apply through Workday
```

and its candidate-account link resolves to `bah.wd1.myworkdayjobs.com`. No directory/vendor inference is required. Booz Allen therefore goes directly to the existing Workday adapter path.

### Sysdig — direct Lever proof with Italy relevance

The current Sysdig operational board is `jobs.lever.co/sysdig`. The current Italy-filtered page contains engineering/security-cloud roles and explicitly says `Jobs powered by Lever`. This is automation-grade platform evidence and a particularly useful target for the project's Europe-first job search.

### Veeam — Greenhouse catalog substantially mirrors first-party

At the audit point:

```text
first-party search: ~228 jobs
Greenhouse root:     224 jobs
```

A four-job difference at a live, changing employer is small enough to justify an immediate API parity probe rather than resolver work. If IDs reconcile after accounting for crawl timing, Veeam should become `COMPLETE_CATALOG_VERIFIED` with one structured source.

### Forter — clean Greenhouse fixture

The current root `forter` is live with 37 jobs and the first-party job-opportunities surface is current. This is a straightforward Greenhouse fast path and a useful additional regression fixture for board-count parity.

### GDIT / SAIC — high-value resolver-light, not blind ATS guesses

Both employers have valuable defense/cyber catalogs visible today, but this batch intentionally leaves the backend unresolved rather than assigning a historical/vendor guess. Their remaining task is narrow: inspect the current search network contract and identify a structured operational source.

## Conservative audit-v2 family floor after 222 mapped employers

Only explicit audit-v2 platform confirmations are counted; backend-unknown rows are excluded.

| Operational family | Minimum audit-v2 employers | Existing adapter? | Strategic meaning |
|---|---:|---:|---|
| Greenhouse | **54+** | Yes | Dominant fast path; Veeam/Forter plus Helsing/Abnormal strengthen vanity-frontend handling |
| Ashby | **29+** | Yes | Major AI/startup/security fast path |
| Workday | **12+** | Yes | Booz Allen adds another high-value defense/cyber enterprise fixture |
| Lever | **4+** | Yes | Sysdig adds a high-value cloud-security fixture |
| Oracle Recruiting Cloud | **3+** | Yes | Solved enterprise family |
| SmartRecruiters | **2+** | Yes | Solved family |
| Avature | **1+** | Yes | Solved family |
| Eightfold | **2+ verified/strong repeated fixtures** | No dedicated adapter | High-priority reusable adapter candidate |
| Teamtailor | **1+** | No | Reusable adapter candidate |
| Talent Gateway / BrassRing | **1+** | No | Reusable adapter candidate |
| Pereless | **1** | No | Recurrence still too low for immediate adapter priority |
| Custom / backend unresolved | still material | N/A | Cheap fingerprint / resolver queue only |

### Verified-family concentration after Batch 19

```text
Greenhouse + Ashby + Workday + Lever
>= 54 + 29 + 12 + 4
>= 99 audit-v2 employer mappings
```

This is now close to one hundred employer mappings covered by just four already-supported adapter families.

## Updated immediate audit queue after Batch 19

### High-ROI direct parity probes

1. Veeam — `veeamsoftware` Boards API vs first-party ~228 jobs.
2. Forter — `forter` Boards API vs first-party.
3. Helsing — derive live Greenhouse board/token from first-party job/apply flow.
4. Abnormal AI — derive/probe root board and compare current first-party IDs.
5. Cloudflare — root Boards API count vs first-party.
6. Okta — enumerate current board identities + scope.
7. SpaceX — main/US source + `spacexglobal` union.
8. CoreWeave — regional first-party surfaces vs Greenhouse union.
9. N26 — root/token proof vs first-party jobs.
10. Aiven / Illumio — derive fresh Greenhouse board identity.

### Resolver-light targets worth inspecting next

1. GDIT
2. SAIC
3. Cyera
4. Orca Security
5. Checkmarx
6. Trellix
7. Leidos
8. General Atomics

### Reusable unsupported platform priority remains

1. Eightfold
2. Talent Gateway / BrassRing
3. Teamtailor
4. SuccessFactors RMK fingerprint completion where adapter already exists
5. Pereless only if recurrence increases
