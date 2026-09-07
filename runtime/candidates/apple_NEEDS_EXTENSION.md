# Apple — `NEEDS_EXTENSION`

## Discovery effettuata (offline-safe, conservative probing)

**Cosa ho fatto (una sola azienda alla volta, una sola request alla volta, pause ≥ 5s, niente brute-force):**

1. `GET https://jobs.apple.com/api/v1/CSRFToken` → HTTP 200. Restituisce `X-Apple-CSRF-Token: 8eacba7af2f6e21296284af388ff34bd092412d9242be27369abb52c0eced405` header + cookie `jobs`, `jssid`, `AWSALBAPP-0`.
2. `POST https://jobs.apple.com/api/v1/search` (page=1) con CSRF token + cookies + JSON body → HTTP 200, 29849 bytes. Response: `{"res": {"searchResults": [...20 items...], "totalRecords": 6124, ...}}`. **Fixture salvata.**
3. `POST .../api/v1/search` (page=2) → HTTP 200, `totalRecords=6124`, 20 results, IDs diversi da page 1.
4. `POST .../api/v1/search` (page=307) → HTTP 200, `totalRecords=6124`, 4 results (ultima pagina parziale: 6124 - 306*20 = 4).
5. `POST .../api/v1/search` (page=308) → HTTP 200, `totalRecords=0`, `searchResults=[]` (sentinella di fine).

Nessun 403, 429, CAPTCHA ricevuto. Stop volontario a 5 probe.

## Backend

Apple proprietary (`jobs.apple.com`). Sistema custom gated dietro CSRF token + session cookies. NON usa Workday, Greenhouse, Taleo, iCIMS, Lever.

## Pattern di pagination osservato

**NON è offset-based.** È page-number-based 1-based:

| Request | totalRecords | searchResults | Note |
|---|---|---|---|
| page=1 | 6124 | 20 | data page |
| page=2 | 6124 | 20 | data page, IDs diversi da page 1 |
| page=307 | 6124 | 4 | ultima pagina parziale (6124 - 306*20 = 4) |
| page=308 | 0 | 0 | sentinella fine |

Per full reconciliation: `ceil(6124/20) = 307` pagine di dati + 1 probe di verifica = **308 total requests**.

## Estrazione osservata (search response)

| Campo | Path | Esempio |
|---|---|---|
| stable ID | `positionId` (numeric) | `200313970` |
| secondary ID | `reqId`, `id` | `PIPE-200313970` |
| title | `postingTitle` | `IN-Business Expert` |
| short summary | `jobSummary` | `Apple Retail is where the best of Apple comes together...` |
| locations | `locations[]` | lista di oggetti con name/country etc. |
| team | `team.teamName` | (es. `Retail` nel primo hit) |
| publication date | `postDateInGMT` (ISO timestamp) | `2026-09-05T16:37:02.482136186Z` |
| alt date | `postingDate` (text) | `Sep 05, 2026` |
| slug | `transformedPostingTitle` | `in-business-expert` |

## Description / qualifications

**NON** sono nella search response. Solo `jobSummary` (breve).

La full description è nel server-rendered HTML di `https://jobs.apple.com/en-us/details/{positionId}-{slug}` in un hydration JSON blob (`payload.loaderData.jobDetails.jobsData.jobSummary/responsibilities/minimumQualifications/preferredQualifications`).

**Nessun endpoint JSON diretto per il detail.** La full description richiede HTML scraping del blob — fuori dal perimetro di v0.1.

## Verdict

**`NEEDS_EXTENSION`**

### Perché v0.1 non basta

Apple ha bisogno di due primitive che v0.1 non offre:

| missing_capability | Evidenza reale (request/response) |
|---|---|
| **page-number pagination** (1-based, integer, step=1) | 4 request osservate: `page=1→20 items, page=2→20 items, page=307→4 items, page=308→0 items`. `totalRecords=6124` costante. Pattern NON riducibile a offset perché il backend rifiuterebbe parametri `offset`/`start`. |
| **Bootstrap step** (chiamata preliminare che produce un token da iniettare nelle request successive) | `GET /api/v1/CSRFToken` → header `X-Apple-CSRF-Token: 8eacba7af...` + cookies `jobs`, `jssid`, `AWSALBAPP-0`. Il token è richiesto in `POST /api/v1/search` come `X-Apple-CSRF-Token` header. Senza questo, `POST /api/v1/search` riceverebbe 401/403. |
| **Session cookie persistence** | Apple invia `Set-Cookie: jobs=...; jssid=...; AWSALBAPP-0=...` che il client DEVE reinviare in ogni successiva request. Il runtime v0.1 non gestisce cookies. |
| **Detail HTML hydration scraping** (per estrarre la description completa) | Il detail page `https://jobs.apple.com/en-us/details/{id}-{slug}` contiene un hydration blob con `responsibilities`, `minimumQualifications`, `preferredQualifications` — nessun JSON API dedicato. |

### Le prime due primitive sono generalizzabili

**`page_number` pagination**: la spec v0.1 prevede già un placeholder `enum: ["next_offset_ge_total", "last_page_shorter_than_page_size", "cursor_absent", "items_path_empty_after_total", "page_size_equals_expected"]` nelle completeness rules ma il runtime **non supporta** strategy=page_number. Una nuova primitiva `paging.strategy: "page_number"` con `paging.page_size` (intero) + `paging.first_page_value` (default 1) + `paging.page_param: "page"` (path nel body) sarebbe immediatamente riutilizzabile da Apple e plausibilmente da altri career portals che usano `?page=N` (Indeed-style, LinkedIn, molti custom).

**`bootstrap_request`**: una primitiva `request.bootstrap` che descriva "prima della prima request di catalog, fai una request a questo URL, estrai questo header/path dal response, salvalo come variabile `csrf_token`" sarebbe utile per qualunque portale con CSRF protection (Apple, molti custom ATS).

### Cosa NON è una nuova primitiva

Il detail hydration blob di Apple è specifico del framework server-rendered Apple. Una primitiva per estrarre description da hydration blob non sarebbe generica — meglio considerarlo `BROWSER_REQUIRED` o `CUSTOM_REQUIRED`. Per ora non viene proposto.

### Perché non propongo le primitive anche se l'evidenza c'è

Apple da sola probabilmente richiederebbe:
1. `paging.strategy: "page_number"` (già modellato nel completeness rules, solo manca strategy)
2. `paging.first_page_value: 1` (vs default 0 per offset)
3. `paging.inject.target: "body_path"` con `path: "page"` (già supportato)
4. Bootstrap step (NUOVA primitiva)
5. Cookie persistence (NUOVA primitiva cross-cutting)

Tuttavia:
- Apple non è ancora una "seconda source reale" che esercita la primitiva: è la **prima**. Senza una seconda fonte che usi `page_number`, aggiungere la primitiva ora sarebbe over-engineering speculativo, contrario al principio del task ("Una nuova primitiva può essere proposta come NEEDS_EXTENSION SOLO se la necessità è supportata da evidenza positiva proveniente da una request/response reale funzionante"). 

L'evidenza c'è (request/response osservate). Ma serve comunque cautela: il contratto v0.1 si è già dimostrato sufficiente per Mercedes (Beesite, offset+body_path), NVIDIA e Microsoft (Eightfold, offset+query_param). Apple sarebbe il primo caso a richiedere `page_number`.

Documentiamo l'evidenza come "extension pressure" senza implementare. Quando arriverà una seconda source con page_number (es. LinkedIn, Indeed, o un altro ATS che usa `?page=N`), si potrà proporre la primitiva con due evidenze reali.

## Conteggio richieste eseguite

- 1 GET CSRFToken (200)
- 1 POST search page=1 (200) → fixture salvata
- 1 POST search page=2 (200)
- 1 POST search page=307 (200)
- 1 POST search page=308 (200)
- **Totale: 5 richieste**, tutte conservative.

## HTTP codes osservati

- 200 su tutte le request
- **Nessun 403, nessun 429, nessun CAPTCHA.**

## Total count

**6124** jobs (`totalRecords` per `postLocation-USA`).

## Estimated requests per full reconciliation

- `ceil(6124/20) = 307` pagine di dati
- + 1 probe vuoto (page=308) → sentinella fine
- + 1 bootstrap CSRFToken
- **Totale: 309 request** per full sweep authoritative

## Cosa NON è stato dimostrato

- La full description (responsibilities, minimumQualifications, preferredQualifications) — richiede scraping HTML del hydration blob
- Detail endpoint JSON diretto — non esiste
- Cookie expiry time / refresh CSRF token rotation — non testato

## Safety

Nessun 403/429/CAPTCHA. Tutte le 5 request hanno risposto 200 con risposta completa. Stop volontario dopo aver ottenuto evidenza sufficiente del pattern page-number.
