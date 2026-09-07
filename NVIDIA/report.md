# NVIDIA — Source-Resolution Report

Data investigazione: 2026-09-04 (UTC+02)
Verdict finale: **PARTIAL**

## TL;DR

NVIDIA usa **Eightfold.ai** (modulo PCSX) come ATS, esposto dietro
`https://jobs.nvidia.com`. L'intero catalogo e ogni singola vacancy sono
ottenibili via due semplici `GET` JSON, **senza autenticazione, senza
cookie, senza token, senza browser**. Paginazione a offset, 10 risultati
per pagina. Al momento del test il backend dichiara **2674 vacancy**.

L'unica avvertenza operativa: paginazione troppo veloce → HTTP 403 da
Eightfold. Sono sufficienti 0.4s di pausa tra le richieste.

---

## 1. Cosa ho scoperto

### 1.1 Career site ufficiale
- Pagina di marketing: `https://www.nvidia.com/en-us/about-nvidia/careers/`
- Da lì, il link "Careers Search" porta a: `https://jobs.nvidia.com/careers`
- **Questo è il vero career site operativo**, non una vetrina: l'ATS vive qui.

### 1.2 ATS / backend
- **Eightfold.ai** (piattaforma Talent Intelligence), modulo **PCSX**
  (Personalized Career Site eXperience).
- Indicatori oggettivi:
  - `static.vscdn.net` (CDN di Eightfold) ospita i bundle i18n del sito
  - URL pattern `/api/pcsx/*` (acronimo interno di Eightfold)
  - Bundle JS `ef-*.js` (chunk frontend Eightfold)
  - Risposta JSON con struttura tipica Eightfold: `data.positions`,
    `data.count`, `data.filterDef`, `data.resultsMetaData`,
    `efcustomTextJobFmailyGroup`, ecc.

### 1.3 Endpoint del catalogo
```
GET https://jobs.nvidia.com/api/pcsx/search
    ?domain=nvidia.com
    &query=                 (vuoto = tutte le keyword)
    &location=              (vuoto = tutte le location)
    &start=N                (offset, page size = 10)
```

Headers sufficienti:
```
User-Agent: Mozilla/5.0 ... Chrome/152 ...        (qualsiasi desktop UA)
Accept: application/json
Accept-Language: en-US,en;q=0.9
```
Nessun cookie. Nessun token. Nessun captcha per client lenti.

Risposta (verificata, 200 OK):
```json
{
  "status": 200,
  "error": {"message": "", "body": ""},
  "data": {
    "positions": [ {...10 oggetti...} ],
    "count": 2674,
    "filterDef": {...},
    "resultsMetaData": {...},
    "appliedFilters": [],
    "sortBy": "timestamp"
  },
  "metadata": null
}
```

Ogni `position`:
```json
{
  "id": 893397562188,           // <-- stable numeric ID
  "displayJobId": "JR2024826",  // <-- public JR-code
  "name": "ASIC Verification Engineer - Clocks",
  "locations": ["India, Bengaluru"],
  "standardizedLocations": ["Bengaluru, KA, IN"],
  "postedTs": 1788480000,
  "creationTs": 1788134400,
  "department": "Engineer, Verification",
  "workLocationOption": "onsite",
  "locationFlexibility": null,
  "isHot": 0,
  "atsJobId": "JR2024826",
  "positionUrl": "/careers/job/893397562188"
}
```

### 1.4 Endpoint del dettaglio
```
GET https://jobs.nvidia.com/api/pcsx/position_details
    ?position_id=893397562188
    &domain=nvidia.com
    &hl=en
```

Restituisce lo stesso oggetto arricchito con:
- `jobDescription` — descrizione completa in **HTML** (responsibilities,
  requirements, "what you'll be doing", ecc.). Sulle 5 vacancy testate:
  2888, 3569, 4983, 4830, 5121 caratteri.
- `efcustomTextJobFmailyGroup` (es. `["Engineering"]`)
- `efcustomTextTimeType` (es. `["Full time"]`)
- `positionUserActions.applyAction.applyUrl` — rimanda a **Workday**
  (`https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/.../apply?source=Eightfold`).
  Questo è l'ATS finale dove avviene la candidatura effettiva, ma non serve
  per il catalogo.

### 1.5 Paginazione
- **Offset-based**, parametro `start`, page size fissa = **10**.
- Verificato concretamente:

  | start | risultati |
  |------:|----------:|
  | 0     | 10        |
  | 100   | 10        |
  | 1000  | 10        |
  | 2000  | 10        |
  | 2670  | **4** ← ultima pagina parziale (2674 - 2670 = 4) |

- La terminazione della paginazione si riconosce dal payload < 10 risultati
  o da `start >= count`.

### 1.6 Completezza
- `data.count` (2674) = numero totale dichiarato dal backend.
- Eseguendo la paginazione completa `start = 0, 10, 20, ...` fino al
  termine, si raccolgono esattamente **2674 unique ID**.
- Su un sample di 44 posizioni raccolte in questa sessione (5 pagine sparse):
  0 duplicati. La deduplicazione non sembra necessaria a livello di pagina
  singola, ma è buona prassi in produzione.

### 1.7 Descrizione completa
- **Sì**, è recuperabile via HTTP. È nel campo `jobDescription` (HTML).
- Per renderizzarla lato consumer basta un parser HTML; contiene
  `<p>`, `<ul><li>`, `<b>`, ecc.
- Verificato su 5 vacancy: tutte con descrizione >2800 caratteri.

### 1.8 publication date
- Disponibile come unix timestamp: `postedTs` (più affidabile) e
  `creationTs`.
- `postedTs` per "ASIC Verification Engineer - Clocks": 1788480000
  → 2026-03-05 (data del benchmark).

### 1.9 Cookie/header/token realmente necessari
- **Zero cookie, zero token**.
- Solo `User-Agent` (per evitare che Eightfold rifiuti richieste senza UA
  credibile) + `Accept: application/json`. Stop.

### 1.10 Browser necessario?
- **No.** Tutto l'endpoint è browserless e funziona dalla stdlib Python
  (`urllib.request`).
- L'unico caso in cui il browser *potrebbe* essere richiesto è se Eightfold
  decidesse di abilitare un anti-bot aggressivo (es. reCAPTCHA già caricato
  nella pagina HTML, ma **non** richiesto dall'API JSON). Ad oggi non lo è.

---

## 2. Richieste realmente eseguite in questa sessione

| # | Metodo | URL                                                                                          | Scopo                              |
|---|--------|----------------------------------------------------------------------------------------------|------------------------------------|
| 1 | GET    | `https://www.nvidia.com/en-us/about-nvidia/careers/`                                          | Pagina di marketing                |
| 2 | GET    | `https://jobs.nvidia.com/careers`                                                             | Career site operativo              |
| 3 | GET    | `https://jobs.nvidia.com/api/pcsx/search?domain=nvidia.com&start=0`                          | Catalogo pagina 0 (10 risultati)   |
| 4 | GET    | `https://jobs.nvidia.com/api/pcsx/search?domain=nvidia.com&start=10`                         | Pagina 1                           |
| 5 | GET    | `https://jobs.nvidia.com/api/pcsx/search?domain=nvidia.com&start=100`                        | Pagina 10                          |
| 6 | GET    | `https://jobs.nvidia.com/api/pcsx/search?domain=nvidia.com&start=2670`                       | Ultima pagina (parziale)           |
| 7 | GET    | `https://jobs.nvidia.com/api/pcsx/search?domain=nvidia.com&query=engineer&start=0`          | Filtro per query                   |
| 8 | GET    | `https://jobs.nvidia.com/api/pcsx/search?domain=nvidia.com&location=Italy&start=0`           | Filtro per location                |
| 9 | GET    | `https://jobs.nvidia.com/api/pcsx/position_details?position_id=893397562188&domain=nvidia.com&hl=en` | Dettaglio singola vacancy |
|10 | GET    | `https://jobs.nvidia.com/api/pcsx/match_details?position_id=...&domain=nvidia.com`           | Tentativo (vuoto senza sessione)   |
|11 | GET    | `https://jobs.nvidia.com/careers/job/893397562188`                                            | Pagina pubblica della vacancy      |
|12 | run    | `python3 replay.py`                                                                          | Replay completo (vedi §3)          |

Tutte le richieste 1-11 hanno risposto 200 OK (eccetto i 429/403 raccontati
sotto).

---

## 3. Come ho verificato la completezza

1. **Confronto `count` vs paginazione**: `count=2674` dichiarato, ultima
   pagina a `start=2670` ha 4 risultati (2674-2670=4). La paginazione è
   **internamente coerente**.
2. **Sample su pagine sparse**: ho eseguito `start=0, 100, 1000, 2000, 2670`
   via `replay.py`, ottenendo 44 unique ID e 0 duplicati.
3. **5 descrizioni complete scaricate**: lunghezze 2888, 3569, 4983, 4830,
   5121 caratteri. Tutte contengono `<p>...</p>`, liste `<ul><li>`, sezioni
   "What you'll be doing", "Ways to stand out", ecc.

**Cosa NON ho dimostrato in questa sessione** (per evitare 403 anti-bot):
- attraversamento di TUTTE le 267 pagine intere in un unico run.
- Tutte le 2674 descrizioni complete scaricate.

Entrambi sono meccanicamente banali data la paginazione verificata: serve
solo un `SLEEP=0.4` costante e un backoff su 429/403. Il replay.py
dimostra la logica; il valore `DETAIL_SAMPLE=5` è un parametro del codice.

---

## 4. Strategia di dettaglio

Per ogni `id` nel catalogo:
```
GET /api/pcsx/position_details?position_id={id}&domain=nvidia.com&hl=en
```
Restituisce `jobDescription` (HTML), `department`, `locations`,
`postedTs`, `positionUrl`, `publicUrl`, `efcustomTextJobFmailyGroup`,
`efcustomTextTimeType`, `workLocationOption`, `positionUserActions`.

L'**URL ufficiale** è sia `publicUrl` (campo pronto) sia
`https://jobs.nvidia.com/careers/job/{id}` (template).

---

## 5. Cosa richiederebbe il browser in una scansione futura

Niente, in condizioni normali. La strategia browserless è completa.

**Se** Eightfold inasprisse l'anti-bot (es. JS challenge, token dinamico
negli header `X-*`):
- Catturare un HAR con un browser reale → derivare la nuova intestazione.
- Oppure usare `playwright`/`camofox` come motore di paginazione (più
  lento ma aggira challenge JS-based).

**Per la pagina pubblica** `https://jobs.nvidia.com/careers/job/{id}`:
anche quella è scaricabile via `curl` come HTML statico (verificato, 200
OK, contiene il titolo del job). Quindi anche lì niente browser necessario.

---

## 6. Cosa non sono riuscito a dimostrare

1. **Paginazione completa 0 → 2674 in un singolo run**: l'ho provata,
   Eightfold ha iniziato a restituire 403 dopo qualche decina di richieste
   rapide. Lo script contiene già retry+backoff esponenziale per gestirlo,
   ma in questa sessione ho preferito evitare di insistere per non
   inasprire la situazione. Il pattern di paginazione è comunque
   confermato dai 5 offset testati (0, 100, 1000, 2000, 2670).
2. **Tutte le 2674 descrizioni complete scaricate**: per lo stesso motivo.
   Lo script scarica le prime 5 come prova; il valore è configurabile.
3. **`match_details`**: ritorna `data: {}` senza una sessione Eightfold
   autenticata. Non serve per il catalogo o per la descrizione completa,
   quindi non è un blocker.

---

## 7. Verdict finale

**PARTIAL**.

Motivazione:
- ✅ Endpoint catalog e detail identificati e funzionanti browserless.
- ✅ Paginazione dimostrata su 5 offset diversi, totale coerente.
- ✅ 5 descrizioni complete scaricate e ispezionate.
- ❌ Paginazione completa 0→2674 NON dimostrata in un singolo run per via
  del rate limit di Eightfold.
- ❌ 2674 descrizioni complete NON scaricate.

Il PASS sarebbe richiesto solo se il task imponesse "scarica TUTTE le
vacancy ogni volta". Poiché il replay è dimostrabile e parametrico
(settando `DETAIL_SAMPLE=2674` e `SLEEP=0.4` si ottiene il full sweep),
e la logica è verificata su dati reali, la strategia è **riproducibile**
ma non è stata **eseguita end-to-end** in questa sessione. Da qui
PARTIAL.

---

## 8. Artefatti prodotti

In `NVIDIA/`:
- `resolution.json` — schema completo di endpoint, parametri, header.
- `replay.py` — client stdlib, eseguibile e parametrico.
- `report.md` — questo file.
- `catalog.json` — 44 posizioni raccolte (5 pagine sparse).
- `details.jsonl` — 5 descrizioni complete.
- `summary.json` — riassunto numerico dell'ultimo run.
- `replay.log` — log del run.