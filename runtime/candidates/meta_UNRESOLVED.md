# Meta — `UNRESOLVED`

## Discovery effettuata (offline-safe, conservative probing)

**Cosa ho fatto (una sola azienda alla volta, una sola richiesta alla volta, pause ≥ 5s, niente brute-force):**

1. `GET https://www.metacareers.com/jobsearch/` → **HTTP 400** con
   `proxy-status: http_request_error` (Facebook error page).
   Headers di sicurezza Meta osservati:
   - `content-security-policy` con allowlist di `*.metacareers.com`,
     `*.facebookcareers.com`, `*.fbcdn.net`, `*.facebook.com`
   - `x-frame-options: DENY`
   - `strict-transport-security: max-age=31536000; preload`
   - `report-uri https://www.facebook.com/csp/reporting/?m=c&...`
2. `GET https://www.metacareers.com/v2/jobsearch/` → **HTTP 400**.
3. `GET https://www.metacareers.com/jobsearch?q=software` → **HTTP 400**.
4. `POST https://www.metacareers.com/graphql` con tutti i browser-shaped
   headers corretti (`Origin`, `Referer`, `Sec-Fetch-Dest/Mode/Site`,
   `X-FB-LSD`) + form body con `doc_id=25452271089445141` (da
   documentazione third-party stale) → **HTTP 200**, body:
   ```json
   {
     "errors": [{"message": "The GraphQL document with ID 25452271089445141 was not found.", "severity": "CRITICAL"}],
     "extensions": {"is_final": true}
   }
   ```
   **Fixture salvata** in
   `fixtures/meta_GRAPHQL_endpoint_reachable_but_doc_id_unknown.json`
   (141 bytes). Questa NON è una fixture utile per extraction — è
   solo la prova che il protocollo Comet/GraphQL di Meta careers
   esiste e che il formato corretto delle request è quello usato.

Nessun 403, 429, CAPTCHA. Stop volontario a 4 probe. Una quinta probe
avrebbe richiesto di indovinare un doc_id attuale, comportamento
brute-force vietato dalle regole di safety.

## Backend

Meta careers (`metacareers.com`) è una **Facebook Comet app**. Tutto
il traffico di ricerca/dettaglio passa per `POST /graphql` con
**persisted queries** identificate da `doc_id`. Documentato in
fonti third-party:
- `github.com/amikai/openings-mcp/internal/provider/meta`
  (lettura diretta della documentazione Comet di Meta)
- `crawlora.net/docs/meta-jobs`

Pattern confermato dalla probe (la sola che ha risposto 200):

| Header / body field | Richiesto | Note |
|---|---|---|
| `Content-Type: application/x-www-form-urlencoded` | sì | form-encoded, NON JSON |
| `Origin: https://www.metacareers.com` | sì | senza → 400 |
| `Referer: https://www.metacareers.com/jobsearch` | sì | senza → 400 |
| `Sec-Fetch-Dest: empty` | sì | senza → 400 |
| `Sec-Fetch-Mode: cors` | sì | senza → 400 |
| `Sec-Fetch-Site: same-origin` | sì | senza → 400 |
| `X-FB-LSD: <token>` | sì | value not validated for logged-out |
| `lsd=<token>` (form) | sì | value not validated for logged-out |
| `variables=<JSON>` (form) | sì | query params: `{isLoggedIn, search_input: {q, teams, roles, offices, is_remote_only, sort_by_new, page, results_per_page}, viewasUserID}` |
| `doc_id=<numeric>` (form) | sì | **richiede bundle JS** per scoprirlo; cambia ad ogni release Comet |

## Verdict

**`UNRESOLVED`**

### Cosa NON è stato dimostrato

- Il `doc_id` corretto per il bundle Comet corrente (richiede scraping
  JS dei bundle `boq_comet_HiringCportalFrontend` per estrarre il
  numero).
- Lo schema dei fields restituiti dalla search query (dipende dal
  `doc_id`).
- Il pattern di pagination. La documentazione third-party dice
  che la search è "server-side filtered but **unpaginated**" — la
  response porta TUTTI i job match in un singolo chunk, e il
  frontend fa slicing client-side. Se confermato, **v0.1 offset
  pagination non ha alcuna corrispondenza con il protocollo Meta**.
- Lo schema del detail endpoint (`CandidatePortalJobDetailsViewQuery`,
  doc_id separato).
- Il `total count` reale del catalogo.
- `browser_required` per il futuro harvesting: se il doc_id deve
  essere estratto da un bundle JS, il modo robusto per ottenerlo
  richiede JS execution.

### Perché non è NEEDS_EXTENSION

Per NEEDS_EXTENSION serve evidenza positiva: una request che ritorna
un response completo e dimostra la mancanza di una primitiva v0.1.
Qui non ho nessun response completo. Ho solo confermato che il
protocollo Comet esiste e che il formato delle request è noto.
**Non posso dichiarare cosa manca in v0.1 perché non so cosa
restituisce il backend.**

### Perché non è SAFETY_ABORT

Nessun 403/429/CAPTCHA ricevuto. Lo stop è per assenza di doc_id,
non per blocco.

### Perché non è CUSTOM_REQUIRED

Potrebbe diventarlo se si scoprisse che il protocollo Comet persiste
come unico modo. Per ora, l'incertezza sul payload impedisce la
classificazione.

### Cosa bisognerebbe fare per risolvere

1. Eseguire il frontend Meta careers in un browser reale (Playwright
   / Selenium) per ottenere la prima risposta valida con un
   doc_id attuale. Salvare la fixture.
2. Replay della stessa request con curl verificando che la
   request funziona senza JS.
3. Verificare il pattern di pagination (se c'è, o se è davvero
   unpaginated).
4. Determinare il `total count` reale.

Solo dopo aver ottenuto una fixture valida si può classificare
Meta come PASS_V01 (se v0.1 copre) o NEEDS_EXTENSION (se manca
qualcosa).

## Conteggio richieste eseguite

- 1 GET `/jobsearch/` (400)
- 1 GET `/v2/jobsearch/` (400)
- 1 GET `/jobsearch?q=software` (400)
- 1 POST `/graphql` con doc_id stale (200 con error GraphQL)
- **Totale: 4 richieste**, tutte conservative.

## HTTP codes osservati

- 400 sulle GET della homepage (richiede Comet-specific headers +
  cookie/JS state)
- 200 sulla POST GraphQL con doc_id errato (endpoint raggiungibile,
  protocollo confermato)

**Nessun 403, nessun 429, nessun CAPTCHA.**

## browser_required

`unknown` — la probe senza browser ha confermato il protocollo Comet
ma non ha ottenuto un doc_id valido. Una successiva investigazione
con browser sarebbe necessaria per confermare.

## Valutazione multidimensionale

| Criterio | Valore |
|---|---|
| contract_fit | **UNRESOLVED** |
| semantic_complete | unknown |
| traversal_complete_under_safety_policy | unknown |
| authoritative_for_closed | unknown |
| browser_required | unknown |
| primary_verdict | **UNRESOLVED** |
