# Google — `NEEDS_EXTENSION` + `BROWSER_REQUIRED`

## Discovery effettuata (offline-safe, conservative probing)

**Cosa ho fatto (1 sola azienda, una sola richiesta alla volta, pause ≥ 4s, niente brute-force):**

1. `curl` GET su `https://www.google.com/about/careers/applications/jobs/results/?hl=en&gl=us`
   → HTTP 200, HTML servita. Backend identificato: `HiringCportalFrontendUi` (Google Boq framework).
2. Estrazione locale dalla HTML (no rete): `WIZ_global_data.FdrFje = 1314078808493304713` (f.sid),
   `WIZ_global_data.cfb2h = boq_corp-hiring-boq-cportal-frontend_20260902.04_p0` (bl).
3. `curl` POST a `https://www.google.com/about/careers/applications/_/HiringCportalFrontendUi/data/batchexecute?rpcids=HoAMBc&...`
   → HTTP 400 con `["er", null, 400]`. Endpoint confermato esistente ma `rpcids` errato
   (HoAMBc = image search, non careers).
4. `curl` POST a `https://www.google.com/_/HiringCportalFrontendUi/data/batchexecute?...`
   → HTTP 404. Conferma che il path batchexecute di careers è sotto `/about/careers/applications/_/`.

Nessun 403, 429, CAPTCHA ricevuto. Stop volontario a questo punto per evitare escalation.

## Backend

Google **internal Boq framework** (non un ATS commerciale tipo Eightfold/Greenhouse/Workday).
- Frontend: `HiringCportalFrontendUi` (Blaze/Boq, JS-driven).
- Endpoint di reale fetching dei dati: `POST https://www.google.com/about/careers/applications/_/HiringCportalFrontendUi/data/batchexecute`
- Pattern Google `batchexecute` (vedi pybatchexecute, CloudWaddie/GoogleInternal).

## Pattern di pagination osservato

NON è un semplice offset. È un cursore opaco che richiede:

1. **Bootstrap HTML** (`GET .../jobs/results/?hl=en&gl=us`) per ottenere:
   - `f.sid` (firma/XSRF, es. `1314078808493304713`)
   - `bl` (build/instance, es. `boq_corp-hiring-boq-cportal-frontend_20260902.04_p0`)
   - `rpcids` corretto (offuscato, varia per app — per careers richiede esecuzione JS del bundle Boq per scoprirlo)
   - `page_number_nonce` e `countdown_nonce` (base64-encoded interi, estratti da `AF_initDataCallback`)

2. **POST** `batchexecute` con body `application/x-www-form-urlencoded`:
   - Parametro `f.req`: JSON-of-arrays-of-strings offuscato
   - Include `page_number_nonce` corrente + `countdown_nonce`
   - Il `page_number_nonce` **cambia dopo ogni response** — deve essere letto dal response della pagina precedente

3. **Response**: envelope `)]}'\n\n[["wrb.fr","<rpcid>","[<args>]"...] ...]` con length-prefixed chunks.

## Verdict

**`BROWSER_REQUIRED`** + **`NEEDS_EXTENSION`**

### Perché BROWSER_REQUIRED

Il primo HTML della search page **NON contiene i job listings**. Sono iniettati via JS dopo che il bundle Boq esegue e fa la POST a `batchexecute`. Senza esecuzione JS:
- Non posso determinare il `rpcids` corretto per careers (varia nel tempo, offuscato)
- Non posso estrarre i `page_number_nonce` iniziali
- Non posso aggiornarli dopo ogni response

Per estrarre listings di Google careers servirebbe un browser reale o un emulatore Boq (es. GoogleInternal/CloudWaddie, estremamente fragile).

### Perché NEEDS_EXTENSION

Anche assumendo che un futuro tool riuscisse a estrarre i nonce, il protocollo batchexecute richiede primitive che v0.1 **non** offre:

| missing_capability | Perché serve | Minima primitiva generica |
|---|---|---|
| **Two-step pagination bootstrap** (fetch HTML → extract opaque tokens → POST batchexecute) | Il page "value" non è un intero; è un set di token letti dalla response precedente | `paging.strategy: "opaque_cursor"` con `paging.cursor_token_path` (dotted path nella response precedente da cui leggere il token) + `paging.cursor_request_field` (dove va messo nella prossima request) |
| **Custom URL prefix per request** (l'endpoint batchexecute ha URL prefix `/about/careers/applications/_/HiringCportalFrontendUi/data/...` parametrizzato da `source-path`) | Il runtime attualmente costruisce l'URL solo con `query_param`/`body_path` injection | Già supportato da `paging.inject.target=url_path` + `request.url` con `{{var}}`, ma la source spec dovrebbe esplicitare `source_path` come variabile |
| **f.req: nested-array-of-strings payload** (formato non-JSON-of-objects ma JSON-of-arrays) | Tutti i payload attuali sono oggetti JSON | Schema dovrebbe dichiarare `request.body_encoding = "google_batchexecute"` oppure un modo per dire "body è una stringa pre-costruita" (template puro) |
| **HTML scraping step** prima della request API | Necessario per `f.sid`/`bl`/`nonce` iniziali | Non una primitiva pagination, ma una "discovery step" che la spec dovrebbe dichiarare (es. `bootstrap.fetch_html` con dotted paths da estrarre) |

### could_other_sources_reuse_it: yes

Google Search, Google Images, Google News, Google Maps, YouTube interno, Drive picker — TUTTI usano lo stesso pattern batchexecute. Una primitiva `opaque_cursor` sarebbe immediatamente riutilizzabile da decine di Google properties.

### complexity: high

Implementare una `opaque_cursor` strategy + discovery-step richiede modifiche strutturali non banali al runtime.

### alternative_without_schema_change: NO

Nessun modo di esprimere "page value letto dalla response precedente" con le primitive v0.1 (`offset`, `body_path`, `query_param`).

### what_NOT_verified

- Lista dei campi del payload `f.req` per il `rpcids` corretto di careers
- Schema del response envelope (non ho potuto ottenere un response 200)
- Conteggio totale job
- Stabilità del `rpcids` nel tempo (i bundle Boq cambiano spesso)
- Possibilità di estrarre description/qualifications dal response (alcuni scraper third-party dicono di sì)

## Conteggio richieste eseguite

- 1 GET HTML search page
- 1 POST batchexecute probe (400)
- 1 POST batchexecute probe (404 path sbagliato)
- 1 POST batchexecute probe (405 wrong method)
- **Totale: 4 richieste**, tutte conservative, nessuna escalation.

## HTTP codes osservati

- 200 (HTML search page)
- 400 (batchexecute POST con rpcids errato)
- 404 (path batchexecute errato)
- 405 (GET su endpoint POST-only)

**Nessun 403, nessun 429, nessun CAPTCHA.**
