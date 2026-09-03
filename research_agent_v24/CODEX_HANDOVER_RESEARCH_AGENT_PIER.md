# CODEX HANDOVER — RESEARCH AGENT - PIER

**Data:** 2026-08-30  
**Stato corrente:** company universe v1 congelato con residui noti; portal resolution completata fino alla Wave 5; MVP non ancora da considerare “finito”.  
**File autorevole da cui ripartire:** `master_company_universe_v1_5_portal_resolution_wave5.csv`

---

## 0. Istruzione principale per Codex

Questo documento è la **single source of truth** per continuare il progetto senza perdere il contesto delle chat precedenti.

Non ricostruire da zero le Wave 1–5 e non rieseguire la discovery dell’universo aziende se non per correggere errori specifici.  
Il master v1.5 è cumulativo e contiene già tutto lo stato di portal resolution raggiunto finora.

L’obiettivo è costruire un MVP locale, affidabile e verificabile di un **job research agent per posizioni cybersecurity junior / internship**, capace di cercare annunci su più fonti, normalizzarli, deduplicarli, filtrarli e mostrarli in una dashboard con analytics.

Il progetto ha due workstream distinti:

1. **Data / Portal Registry**
   - universo aziende;
   - risoluzione dei career portal;
   - mapping ATS;
   - parent/acquisition normalization;
   - continuazione Wave 6+.

2. **MVP Job Scanner**
   - scansione LinkedIn + career site ufficiali;
   - adapter ATS;
   - parsing annunci;
   - filtro cyber + junior/internship;
   - dedup;
   - persistenza;
   - dashboard/analytics.

Non confondere i due workstream: la portal resolution non deve essere rifatta a ogni job scan.

---

# 1. Problema da risolvere

L’utente sta cercando ruoli **cybersecurity junior e internship** in Italia e all’estero.

Il problema di base è che:

- LinkedIn non contiene necessariamente tutti gli annunci;
- molte aziende pubblicano vacancy solo sul proprio careers portal;
- le vacancy possono essere duplicate tra LinkedIn, ATS e sito ufficiale;
- cercare manualmente centinaia/migliaia di aziende non scala;
- un crawler ingenuo con migliaia di richieste può causare rate limit, blocchi IP, costi eccessivi e risultati rumorosi.

Il sistema deve quindi diventare un ricercatore automatico, ma per l’MVP deve restare **semplice, locale e manualmente avviato**.

---

# 2. Scope MVP deciso

## 2.1 Modalità di esecuzione

Per ora:

- gira **in locale sul PC**;
- la ricerca parte **su comando**;
- nessun daemon obbligatorio;
- nessun cron obbligatorio;
- niente infrastruttura cloud necessaria per il primo MVP;
- deve però essere progettato in modo che in futuro sia facile schedularlo.

## 2.2 Fonti

Priorità prodotto:

1. **LinkedIn**
2. **sito careers ufficiale di ogni azienda**
3. ATS / job board ufficiale collegato al sito careers

Nota tecnica importante:

LinkedIn è una fonte prioritaria per il prodotto, ma **l’architettura non deve dipendere da scraping aggressivo di LinkedIn**.  
Non implementare bypass di login, CAPTCHA, rate limit o meccanismi anti-bot.

Se non esiste un metodo compliant e stabile per high-volume LinkedIn discovery, lascia l’adapter isolato/attivabile e rendi i career portal ufficiali la fonte robusta di ground truth.

## 2.3 Cosa NON serve nell’MVP

Per ora NON implementare:

- people research;
- ricerca recruiter / hiring manager;
- scoring rispetto al CV;
- matching semantico con il CV;
- senior roles;
- espansione a ruoli SWE generici;
- automazioni cloud complesse;
- sistemi distribuiti;
- GPU/LLM obbligatori.

La dashboard e le analytics invece **servono già nell’MVP**.

---

# 3. Geografie target

Scope concordato:

- tutti i paesi UE;
- UK;
- Irlanda;
- Svizzera;
- Norvegia;
- USA;
- Canada;
- Singapore;
- Australia.

**Italia è assolutamente inclusa.**

**Middle East escluso.**

New Zealand compare in alcune righe del company universe per motivi di discovery/parent group, ma **non va considerata automaticamente una nuova geografia target** finché non viene esplicitamente aggiunta.

### UE da trattare come set configurabile

Austria, Belgium, Bulgaria, Croatia, Cyprus, Czechia, Denmark, Estonia, Finland, France, Germany, Greece, Hungary, Ireland, Italy, Latvia, Lithuania, Luxembourg, Malta, Netherlands, Poland, Portugal, Romania, Slovakia, Slovenia, Spain, Sweden.

La geografia deve stare in configurazione, non hardcoded in più file.

### Regola importante

Non filtrare brutalmente le aziende usando solo `Discovery Geography`.

Un’azienda può essere `Multi-region`, USA-based o classificata con una geografia di discovery ma pubblicare vacancy in Europa.

Il filtro geografico finale deve essere applicato **alla vacancy**, non soltanto alla sede dell’azienda.

---

# 4. Ruoli target

## 4.1 Seniority inclusa

Includere:

- Internship
- Intern
- Stage
- Trainee
- Graduate
- New Grad
- Entry Level
- Junior
- Apprentice
- Working Student
- Thesis / student opportunities quando chiaramente cyber

Possibile estensione futura: ruoli con 0–2/3 anni di esperienza anche se non esplicitamente marcati junior.

## 4.2 Seniority da escludere

Di default escludere titoli contenenti chiaramente:

- Senior
- Staff
- Principal
- Lead
- Manager
- Director
- Head
- VP / Vice President
- CISO
- Distinguished
- Fellow

Le regole devono essere configurabili e testate.

## 4.3 Cyber scope

L’utente vuole una ricerca **molto esaustiva**, non limitata a SOC/pentesting.

La tassonomia deve includere almeno:

- Cybersecurity
- Cyber Security
- Information Security
- InfoSec
- Security Engineering
- Security Analyst
- Security Operations / SOC
- Incident Response
- DFIR
- Threat Intelligence / CTI
- Threat Hunting
- Detection Engineering
- SIEM / SOAR
- Application Security / AppSec
- Product Security
- Cloud Security
- DevSecOps
- Vulnerability Management
- Vulnerability Research
- Penetration Testing
- Offensive Security
- Red Team
- Blue Team
- Malware Analysis
- Reverse Engineering quando security-related
- IAM
- PAM
- IGA
- Identity Security
- GRC
- Governance
- Risk
- Cyber Risk
- IT Risk
- Security Compliance
- Security Assurance
- Security Audit
- Security Architecture
- Security Research
- Cryptography / Cryptographic Engineering
- PKI
- Network Security
- Endpoint Security
- OT Security
- ICS Security
- Industrial Cybersecurity
- Automotive Cybersecurity
- Embedded Security
- IoT Security
- Security Testing
- Privacy Engineering / Privacy Security quando tecnicamente pertinente
- Third Party Cyber Risk
- Security Governance
- Security Controls
- Security Program / Security Operations support junior
- Digital Forensics

Non ampliare invece a **Software Engineer generico**.

Un `Security Engineer` rimane in scope perché è cyber; un `Software Engineer` non security-related no.

Le keyword devono stare in file/config dedicati e non essere replicate in codice sparso.

---

# 5. Stato del company universe

File cumulativo corrente:

`master_company_universe_v1_5_portal_resolution_wave5.csv`

Metriche verificate:

- **12.503 record**
- **11.798 Corporate Cluster ID unici**
- `Record ID` tutti unici
- nessun `Corporate Cluster ID` vuoto
- **12.437** record `Career Scan Eligible = Yes`
- **66** record `Career Scan Eligible = Secondary`
- tutti i record hanno `Freeze Status = FROZEN_WITH_KNOWN_RESIDUALS`

Il company universe v1 è quindi considerato congelato con residui noti.

Non significa che la portal resolution sia completa.

## 5.1 Stato portal resolution

Dopo Wave 5:

- **575 corporate cluster risolti**
- **1.263 master record coperti**
- **10,10%** di copertura record
- **11.240 record** ancora `NOT_STARTED`
- **11.223 cluster** ancora senza resolution wave
- **510 Jobs Search URL unici** tra i 575 cluster risolti

Questo ultimo dato è importante: **non bisogna fare una request per ogni record**.

Molti record/cluster condividono portali.

---

# 6. Progressione delle Wave

| Wave | Cluster risolti | Record master coperti |
|---|---:|---:|
| W1 | 47 | 455 |
| W2 | 73 | 321 |
| W3 | 161 | 184 |
| W4 | 153 | 161 |
| W5 | 141 | 142 |
| **Totale** | **575** | **1.263** |

## Wave 3

- 161 cluster
- 184 record
- cumulativo: 960 / 12.503 = 7,68%

Portali condivisi importanti:

- DNB: 10 cluster
- Barclays: 9
- Nokia: 7
- Mediobanca: 5
- Ericsson: 5
- Indra: 4
- Telenor: 4
- Prysmian: 3
- Banco BPM: 3
- Rolls-Royce: 3
- altri shared portal minori

## Wave 4

- 153 cluster
- 161 record
- cumulativo: 1.121 / 12.503 = 8,97%

Normalizzazioni / casi notevoli:

- DB Schenker → careers DSV
- HashiCorp → IBM Careers per le vacancy correnti
- Armis → ServiceNow parent openings
- Digital Realty → Oracle Recruiting Cloud
- Eaton → Eightfold
- Tenaris → SuccessFactors
- Italgas → careers site dedicato

Sono rimasti 17 cluster prioritari ambigui/non forzati. Tra i nomi incontrati:

- ACS / acs
- AEC Andalo
- AIR
- AMAGA
- AMAN
- ASE
- Aircraft Appliances and Equipment
- Aircraft Appliances and Equipment (trading Trident Maritime Systems Canada)
- COABSER
- Dynamic Ear Company
- EASP AIR NL
- EID
- GO
- Hypo Tirol Bank
- I.E.S / IES
- PPC Energie
- PPC Renewables România
- PPC Servicii Comune
- SMA

Il numero di nomi è maggiore dei cluster perché alcuni sono alias/varianti.

## Wave 5

Focus:

- global cybersecurity vendors;
- high-value Australian mining/resources;
- Australian banks/insurers;
- grandi employer tech/finance/industrial USA.

Risultato:

- 150 cluster analizzati
- 141 cluster risolti
- 142 record master coperti
- cumulativo: 1.263 / 12.503 = 10,10%

Parent/acquisition normalization notevoli:

- Astrix Security → Cisco
- Lacework → Fortinet
- Noname Security → Akamai
- Protect AI → Palo Alto Networks
- Red Canary → Zscaler
- Traceable AI → Harness
- Vulcan Cyber → Tenable
- Suncorp Bank → ANZ Group
- Heritage and People's Choice → People First Bank
- Auswide Bank → MyState Limited
- AAI → Suncorp Group
- IAG New Zealand → IAG
- Insurance Australia → IAG

9 cluster volutamente deferred:

1. Keep Security
2. Permiso
3. Australian Settlements
4. Bank of China Australia
5. Cairns Bank
6. Aioi Nissay Dowa Insurance Australia
7. ANZ Lenders Mortgage Insurance
8. Defence Service Homes Insurance Scheme
9. Hallmark General Insurance

Non forzare mapping poco sicuri.

---

# 7. File consegnati con la Wave 5

Archivio:

`research_agent_portal_resolution_wave5.zip`

Contiene:

1. `master_company_universe_v1_5_portal_resolution_wave5.csv`
2. `portal_resolution_wave5.csv`
3. `portal_resolution_wave5_mapping_audit.csv`
4. `portal_resolution_wave5_summary.json`

Il **master v1.5** è il file autorevole cumulativo.

`portal_resolution_wave5.csv` contiene solo le resolution della Wave 5.

`portal_resolution_wave5_mapping_audit.csv` serve per audit umano.

`portal_resolution_wave5_summary.json` contiene metriche, deferred e normalizzazioni.

Non assumere che lo ZIP Wave 5 contenga gli audit CSV delle Wave 1–4.  
Le informazioni cumulative necessarie per lo scanner sono già nel master.

---

# 8. Schema del master v1.5

Colonne esatte:

```text
Record ID
Employer
Canonical Employer
Parent Group
Corporate Cluster ID
Canonical Name Occurrences
Duplicate Review Flag
Entity Class
Career Scan Eligible
Sector
Discovery Geography
Org Type
Corporate Website
Website Status
Careers URL
Career Scan Status
Discovery Source
Source URL
Notes
Freeze Version
Freeze Status
Resolved Corporate Website
Resolved Careers Landing URL
Resolved Jobs Search URL
Portal Scope
ATS Family
ATS Confidence
Portal Resolution Status
Portal Verification URL
Portal Verified Date
Resolution Parent Override
Resolution Wave
```

## Chiavi

### `Record ID`

Primary key della riga del master.

### `Corporate Cluster ID`

Chiave principale per deduplicare entità aziendali.

Tutte le operazioni di portal resolution devono ragionare prima per cluster, non per singolo record.

### URL da usare per lo scanner

Quando `Portal Resolution Status` è verificato:

- corporate site:
  `Resolved Corporate Website`
- careers landing:
  `Resolved Careers Landing URL`
- job board/search:
  `Resolved Jobs Search URL`

Per lo scanning delle vacancy, `Resolved Jobs Search URL` è normalmente il punto di partenza più utile.

### `Resolution Parent Override`

Indica casi in cui il brand/legal entity deve usare il parent careers portal.

Non ignorare questo campo.

### `ATS Family`

È metadata operativo.

Non inventare il vendor.

Se la Wave ha scritto:

`Custom / backend unverified`

va mantenuto così finché non emerge prova concreta.

### `ATS Confidence`

Valori osservati:

- `Verified`
- `High`
- `Medium-High`

`High` NON equivale automaticamente a `Verified`.

### `Portal Scope`

È free-text metadata, non enum rigido.

Non creare logica fragile basata su un elenco chiuso dei valori osservati.

---

# 9. File Wave 5: schema portal resolution

`portal_resolution_wave5.csv`:

```text
Corporate Cluster ID
Resolved Group
Representative Employer
Legal/Discovery Records Covered
Corporate Website
Careers Landing URL
Jobs Search URL
Portal Scope
ATS Family
ATS Confidence
Resolution Status
Verification Evidence URL
Verified Date
Parent Override
Shared Portal Group
Notes
```

Questo formato va mantenuto per Wave 6+ salvo necessità motivata.

---

# 10. Regole di portal resolution

Quando si continua con Wave 6+:

1. partire solo da cluster `NOT_STARTED`;
2. deduplicare per `Corporate Cluster ID`;
3. preferire:
   - grandi employer;
   - aziende cyber;
   - aziende nei paesi principali;
   - cluster con più record;
   - company seed strategiche;
4. trovare il **sito corporate ufficiale**;
5. trovare la **careers landing ufficiale**;
6. trovare il **vero jobs search endpoint**;
7. identificare ATS solo con evidenza;
8. se brand acquisito:
   - verificare se careers è ancora autonomo;
   - altrimenti usare parent override;
9. non associare portali per semplice somiglianza del nome;
10. non forzare entità ambigue;
11. aggiornare `Portal Verified Date`;
12. preservare le Wave precedenti.

## Output richiesto per ogni nuova Wave

Produrre:

- `portal_resolution_waveN.csv`
- `master_company_universe_v1_N_portal_resolution_waveN.csv`
- `portal_resolution_waveN_mapping_audit.csv`
- `portal_resolution_waveN_summary.json`
- ZIP finale

## Validazioni obbligatorie

A fine Wave:

- nessun `Record ID` duplicato;
- nessun cluster nuovo duplicato nel file Wave;
- `Legal/Discovery Records Covered` deve sommare esattamente ai master row aggiornati;
- non modificare righe già verificate in W1–W5 se non per una correzione esplicita;
- tutte le righe della nuova wave devono avere:
  - URL careers;
  - URL jobs;
  - verification URL;
  - verified date;
  - resolution wave;
- ZIP apribile;
- metriche cumulative coerenti.

---

# 11. Principio fondamentale: NON fare 12.503 query ogni run

Uno dei problemi già identificati è il rischio di immaginare:

> 12k aziende = 12k query contemporanee

È il modello sbagliato.

La pipeline deve separare:

### A. Discovery / portal resolution

Operazione lenta e incrementale.  
Si esegue una volta per risolvere un’azienda/cluster e poi si salva il risultato.

### B. Job scanning

Operazione ricorrente sui portal già noti.

### C. Job details

Fetch solo per annunci nuovi/cambiati quando necessario.

Inoltre:

- 12.503 master rows ≠ 12.503 aziende uniche;
- ci sono 11.798 cluster;
- i portal risolti attuali sono 575 cluster;
- gli URL jobs unici sono 510.

Quindi già oggi lo scanner può lavorare su ~510 endpoint unici, non su 1.263 record e certamente non su 12.503 URL.

---

# 12. Criticità tecniche e soluzioni

## 12.1 IP ban / rate limiting

Problema reale se il crawler viene implementato male.

Soluzioni:

- queue per dominio;
- rate limit per host;
- global concurrency limit;
- jitter;
- exponential backoff;
- rispettare `Retry-After`;
- cache;
- conditional requests quando supportate;
- evitare refresh inutili;
- usare endpoint JSON/pubblici dell’ATS quando esistono;
- scansioni incrementali;
- evitare browser automation quando basta HTTP;
- non usare proxy rotation per aggirare blocchi;
- non bypassare CAPTCHA o access control.

Default conservativo per MVP:

- global concurrency: ~8
- per-domain concurrency: 1
- pochi retry, ad esempio 2–3
- backoff esponenziale su 429/5xx
- timeout ragionevole, ad esempio 15–30 s

Questi parametri devono stare in config.

## 12.2 Server power

Il workload è principalmente **I/O bound**, non GPU-bound.

Per l’MVP:

- 4 core CPU sono sufficienti;
- 8 GB RAM può funzionare;
- 16 GB RAM è più comodo;
- GPU non necessaria;
- SQLite sufficiente all’inizio.

Playwright/headless browser è la parte più pesante.

Non aprire decine/centinaia di browser context simultanei.

Usare browser fallback con pool molto piccolo, ad esempio 1–2 context/pagine concorrenti.

## 12.3 JavaScript-heavy career sites

Strategia:

1. HTTP/JSON adapter specifico ATS
2. HTML parser
3. embedded JSON / script state
4. Playwright solo fallback

Non partire da Playwright per tutto.

## 12.4 Cambi ATS / acquisizioni / link rot

Ogni portal deve avere:

- last verified;
- last successful scan;
- failure counter;
- HTTP status;
- optional redirect target;
- health state.

Se un URL cambia:

- non cancellare subito la vecchia relazione;
- segnare stale/broken;
- tentare careers landing;
- tentare corporate site;
- eventualmente mandare il cluster in `NEEDS_RERESOLUTION`.

## 12.5 False positive cyber

Fare filtering a più stadi:

1. title keyword
2. description keyword
3. negative keyword / context
4. seniority
5. geography
6. eventuale classificatore/LLM solo per casi ambigui

Non usare un LLM su ogni vacancy: costoso e non necessario.

## 12.6 Duplicate job

Ordine preferito per dedup:

1. `(source, source_job_id)`
2. canonical application URL
3. ATS job ID
4. hash normalizzato di:
   - canonical company/cluster
   - title
   - location
   - requisition id
5. fuzzy matching solo come fallback

LinkedIn e official portal possono descrivere lo stesso job: mantenere entrambe le source provenance ma un singolo job canonico.

## 12.7 Job stale/expired

Ogni job deve avere almeno:

- `first_seen_at`
- `last_seen_at`
- `is_active`
- `closed_at` opzionale
- source publication date quando disponibile

Un job non visto in una singola scansione non deve essere immediatamente cancellato se la source ha avuto errori.

## 12.8 Schema drift

Ogni adapter ATS deve essere isolato e avere test fixture.

Se Workday cambia, non deve rompere Greenhouse.

## 12.9 Data provenance

Ogni campo importante deve poter essere ricondotto a:

- source;
- source URL;
- fetch timestamp;
- raw/source job id;
- parser/adapter.

Questo è fondamentale per debug.

---

# 13. Architettura MVP consigliata

Implementazione semplice e mantenibile.

## Stack suggerito

- Python 3.12+
- `uv` o equivalente per gestione ambiente
- `pydantic` / `pydantic-settings`
- `httpx`
- `lxml`, `selectolax` o BeautifulSoup
- Playwright solo fallback
- `tenacity` o retry equivalente
- SQLite
- SQLAlchemy / SQLModel
- Typer per CLI
- Streamlit per dashboard MVP
- pytest

Non introdurre microservizi.

---

# 14. Struttura repository consigliata

```text
research-agent/
├── README.md
├── pyproject.toml
├── .env.example
├── config/
│   ├── settings.yaml
│   ├── geographies.yaml
│   ├── cyber_keywords.yaml
│   └── seniority.yaml
│
├── data/
│   ├── company_universe/
│   │   └── master_company_universe_v1_5_portal_resolution_wave5.csv
│   ├── portal_resolution/
│   │   └── ...
│   ├── raw/
│   └── exports/
│
├── src/
│   └── research_agent/
│       ├── __init__.py
│       ├── cli.py
│       ├── config.py
│       ├── logging.py
│       │
│       ├── db/
│       │   ├── models.py
│       │   ├── session.py
│       │   └── migrations.py
│       │
│       ├── company/
│       │   ├── importer.py
│       │   ├── clustering.py
│       │   └── portal_registry.py
│       │
│       ├── sources/
│       │   ├── base.py
│       │   ├── linkedin/
│       │   ├── official/
│       │   └── ats/
│       │       ├── greenhouse.py
│       │       ├── lever.py
│       │       ├── ashby.py
│       │       ├── recruitee.py
│       │       ├── comeet.py
│       │       ├── smartrecruiters.py
│       │       ├── successfactors.py
│       │       ├── workday.py
│       │       ├── oracle.py
│       │       ├── phenom.py
│       │       └── generic.py
│       │
│       ├── pipeline/
│       │   ├── scanner.py
│       │   ├── normalizer.py
│       │   ├── filter.py
│       │   ├── dedup.py
│       │   └── lifecycle.py
│       │
│       ├── filters/
│       │   ├── cyber.py
│       │   ├── seniority.py
│       │   └── geography.py
│       │
│       └── dashboard/
│           └── app.py
│
├── tests/
│   ├── fixtures/
│   ├── test_import_master.py
│   ├── test_filters.py
│   ├── test_dedup.py
│   └── test_adapters_*.py
│
└── scripts/
    ├── validate_master.py
    └── export_jobs.py
```

Non è obbligatorio usare esattamente questi nomi, ma mantenere la separazione concettuale.

---

# 15. Modello dati minimo

## CompanyRecord

Rappresenta la riga originaria del master.

Chiave:

`record_id`

## CorporateCluster

Chiave:

`corporate_cluster_id`

Campi principali:

- canonical employer
- parent group
- entity class
- scan eligible
- sector
- discovery geography

## Portal

Un portal può essere condiviso da più cluster.

Campi:

- portal_id
- corporate website
- careers landing URL
- jobs search URL
- ATS family
- ATS confidence
- portal scope
- verified date
- parent override
- normalized jobs URL
- health state
- last successful scan
- last failure
- consecutive failures

Serve una relazione many-to-many cluster ↔ portal se necessario.

## ScanRun

- run_id
- started_at
- finished_at
- source
- portal count
- success count
- failure count
- jobs discovered
- new jobs
- updated jobs
- duplicates
- error summary

## SourceJob

Rappresenta la vacancy così come osservata da una source.

Campi minimi:

- source
- source_job_id
- source_url
- apply_url
- raw_title
- raw_company
- raw_location
- raw_description
- posted_at
- fetched_at
- raw payload / snapshot reference

## CanonicalJob

Campi consigliati:

- canonical_job_id
- corporate_cluster_id
- title
- normalized_title
- location
- country
- city
- remote/hybrid/onsite
- description
- employment_type
- seniority
- cyber_category
- posted_at
- first_seen_at
- last_seen_at
- active
- closed_at

Relazione SourceJob → CanonicalJob per mantenere provenance multi-source.

---

# 16. Pipeline di scanning

```text
LOAD CONFIG
    ↓
LOAD PORTAL REGISTRY
    ↓
SELECT ELIGIBLE UNIQUE PORTALS
    ↓
GROUP BY HOST / ATS
    ↓
RATE-LIMITED FETCH
    ↓
ATS-SPECIFIC OR GENERIC PARSER
    ↓
NORMALIZE JOB
    ↓
CYBER FILTER
    ↓
SENIORITY FILTER
    ↓
GEOGRAPHY FILTER
    ↓
DEDUP SOURCE JOB
    ↓
CROSS-SOURCE DEDUP
    ↓
UPSERT DB
    ↓
UPDATE JOB LIFECYCLE
    ↓
RUN METRICS
    ↓
DASHBOARD
```

---

# 17. ATS/adapters

Esempi già verificati nel dataset:

- Greenhouse
- Lever
- Ashby
- Recruitee
- Comeet
- SmartRecruiters
- Workday
- SAP SuccessFactors
- Oracle Recruiting Cloud
- Taleo-style
- Eightfold
- Phenom-style
- molti custom/branded portals

Distribuzione indicativa sui 575 cluster risolti:

- `Custom / backend unverified`: 184 cluster
- `Custom / branded portal`: 95
- `SAP SuccessFactors Recruiting Marketing-style`: 68
- `Custom first-party portal`: 35
- `Custom first-party job board`: 27
- `Custom / branded jobs portal`: 16
- `Phenom-style branded portal / backend unverified`: 16
- `Workday`: 13
- `Greenhouse`: 11
- altri ATS: long tail

Quindi:

- servono adapter specifici per gli ATS strutturati;
- serve comunque un `generic` adapter robusto;
- non cercare di creare un unico parser universale enorme.

---

# 18. LinkedIn

Requisito prodotto: LinkedIn è la prima fonte desiderata.

Vincoli architetturali:

- adapter isolato;
- non far dipendere l’intero scanner da LinkedIn;
- niente bypass tecnici;
- niente crawling aggressivo;
- niente migliaia di browser page simultanee;
- cache e incremental discovery;
- se un job LinkedIn punta al career site ufficiale, conservare entrambe le provenance;
- official ATS può diventare source canonica per dati completi.

Possibile MVP:

- LinkedIn discovery limitata / controllata;
- official portals come verifica e fonte completa;
- dedup tra le due.

---

# 19. Dashboard MVP

La dashboard deve essere utile già subito.

Metriche minime:

## Jobs

- total active jobs
- new jobs nell’ultimo run
- new jobs oggi / ultimi N giorni
- jobs per country
- jobs per company
- jobs per cyber category
- jobs per seniority
- internship vs junior
- remote / hybrid / onsite
- source distribution
- LinkedIn-only
- official-only
- found on both

## Coverage

- total company records
- total corporate clusters
- resolved clusters
- unresolved clusters
- unique portals
- scanned portals
- healthy portals
- broken portals
- stale portals
- coverage per geography
- coverage per sector
- coverage per ATS

## Scanner health

- last run
- duration
- requests
- 2xx / 3xx / 4xx / 5xx
- 429 count
- retries
- failed domains
- parser failures
- empty portal anomaly
- jobs discovered
- new
- changed
- expired
- duplicates

Filtri UI:

- country
- company
- keyword/cyber category
- seniority
- internship/junior
- source
- date discovered
- remote/hybrid/onsite
- active/expired

Tabella job con link diretto all’annuncio/application URL.

---

# 20. Ordine di implementazione consigliato

## Milestone 0 — bootstrap

- crea repo skeleton;
- configura Python;
- logging;
- config;
- pytest;
- SQLite.

## Milestone 1 — import master

Importare il master v1.5.

Acceptance test:

```text
rows = 12,503
unique Record ID = 12,503
unique Corporate Cluster ID = 11,798
resolved rows = 1,263
resolved clusters = 575
unique resolved Jobs Search URL ≈ 510
```

Non proseguire se questi numeri non tornano.

## Milestone 2 — portal registry

Creare tabella portal + mappings cluster↔portal.

Deduplicare gli scan tramite normalized `Resolved Jobs Search URL`.

## Milestone 3 — scanner core

Implementare:

- queue;
- host limiter;
- retries;
- caching;
- run logging;
- raw response persistence opzionale/compressa.

## Milestone 4 — primi ATS adapter

Priorità pragmatica:

1. Greenhouse
2. Lever
3. Recruitee
4. Ashby
5. SmartRecruiters
6. SuccessFactors
7. Workday
8. Oracle/Taleo
9. Phenom
10. generic/custom

L’ordine può essere riaggiustato dopo aver calcolato la copertura reale degli URL correnti.

## Milestone 5 — filter + dedup

- cyber taxonomy;
- junior/intern taxonomy;
- geo parser;
- exact/stable dedup;
- cross-source dedup.

## Milestone 6 — dashboard

Streamlit MVP.

## Milestone 7 — LinkedIn adapter

Integrarlo senza compromettere stabilità e compliance del resto del sistema.

## Milestone 8 — Wave 6+

Continuare la portal resolution sui cluster ad alto valore mentre il crawler è già testabile sui portal esistenti.

---

# 21. Strategia Wave 6+

Non tentare di risolvere 11.223 cluster tutti insieme.

Continuare a wave, circa 100–200 corporate cluster per volta.

Priorità:

1. grandi employer ancora scoperti;
2. cyber vendors;
3. aziende target dei paesi principali;
4. cluster con più master record;
5. aziende provenienti da `Research seed - cross-sector`;
6. grandi banche/assicurazioni/tech/industrial/defence;
7. solo dopo il long tail di directory associative.

La Wave 5 ha già portato il coverage al 10,10%.

Il valore marginale ora deve essere misurato non solo in “record coperti”, ma anche in:

- numero di vacancy potenziali;
- qualità dell’ATS;
- importanza dell’employer;
- geografie target;
- probabilità di junior/intern roles.

---

# 22. Cose da NON fare

- non rifare l’universo aziende da zero;
- non perdere le provenance;
- non modificare silenziosamente una resolution esistente;
- non inventare ATS;
- non deduplicare soltanto per nome azienda;
- non assumere che `Employer` sia l’identità canonica;
- non fare una query per ogni master row;
- non lanciare Playwright massivamente;
- non usare LLM su ogni vacancy;
- non aggiungere Middle East;
- non aggiungere SWE generico;
- non introdurre people research;
- non introdurre CV-fit;
- non costruire microservizi per l’MVP;
- non usare GPU come requisito;
- non bypassare anti-bot / CAPTCHA / login;
- non cancellare job solo perché mancano da un run fallito.

---

# 23. Definition of Done dell’MVP

L’MVP è accettabile quando:

1. importa correttamente il master v1.5;
2. usa Corporate Cluster ID e portal dedup;
3. può essere avviato manualmente;
4. scansiona un set significativo di career portal risolti;
5. ha almeno alcuni ATS adapter reali;
6. gestisce rate limiting/backoff;
7. normalizza vacancy;
8. filtra cyber;
9. filtra junior/intern;
10. filtra geografia;
11. deduplica le vacancy;
12. persiste lo storico;
13. distingue nuovi/attivi/chiusi;
14. produce metriche di run;
15. mostra una dashboard consultabile;
16. nessuna dipendenza obbligatoria da LinkedIn scraping fragile;
17. test automatici sui componenti critici;
18. un singolo errore di portale non blocca l’intero run.

---

# 24. Primo task che Codex deve eseguire

Se hai accesso al repository e allo ZIP Wave 5:

1. estrai/copialo sotto `data/company_universe/`;
2. crea la struttura MVP;
3. implementa l’importer;
4. scrivi i test sulle metriche note;
5. crea il portal registry deduplicato;
6. stampa un report con:
   - 12.503 rows;
   - 11.798 cluster;
   - 575 resolved cluster;
   - 1.263 resolved rows;
   - ~510 unique resolved job URLs;
7. solo dopo implementa lo scanner.

Non partire dal web crawling prima di aver validato il data model.

---

# 25. Prompt operativo per Codex

Puoi usare questo testo come istruzione iniziale:

> Stai continuando il progetto `RESEARCH AGENT - PIER`. Leggi integralmente `CODEX_HANDOVER_RESEARCH_AGENT_PIER.md` e considera `master_company_universe_v1_5_portal_resolution_wave5.csv` la fonte autorevole dello stato corrente. Non ricostruire le Wave 1–5. Implementa l’MVP local-first descritto nel handover, procedendo per milestone e mantenendo test automatici. Prima milestone: import del master, data model e portal registry con metriche di acceptance esatte. Non fare scraping massivo, non bypassare anti-bot e non introdurre scope non richiesto. Quando devi scegliere tra una soluzione complessa e una semplice che soddisfa l’MVP, preferisci la semplice. Itera sul codice fino a quando test e acceptance criteria della milestone corrente passano, poi continua con la milestone successiva. Documenta decisioni e modifiche importanti nel repository.

---

# 26. Note finali

La parte più importante del progetto è mantenere tre livelli separati:

```text
COMPANY UNIVERSE
        ↓
PORTAL REGISTRY
        ↓
JOB OBSERVATIONS
```

Il company universe cambia lentamente.

Il portal registry cambia occasionalmente.

Le vacancy cambiano continuamente.

Questa separazione evita di rifare discovery costosa e riduce enormemente il numero di richieste.

Il master v1.5 attuale è già sufficiente per costruire e testare un MVP reale su centinaia di portal prima di completare la resolution dell’intero universo.

**Ripartire da qui.**
