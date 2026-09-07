# Source Spec v0.1 — Report (frozen)

## Cos'è

Questo step definisce un **contratto dichiarativo** (`runtime/source_spec.schema.json`) che descrive COME parlare con una fonte di vacancy, senza scrivere Python specifico per fonte. Lo schema è già in grado di rappresentare Mercedes-Benz e NVIDIA sulla base dei soli artefatti locali (`mb/` e `NVIDIA/`).

A partire da questo step esiste anche un **esecutore offline source-agnostic** (`runtime/spec_executor.py`) che interpreta la spec e produce:
- la struttura della request HTTP (method, url, headers, query, body)
- l'injection dell'offset dove dichiarato da `paging.inject`
- l'estrazione dei campi della vacancy via dotted JSON path
- la normalizzazione nello schema `job.schema.json`
- la decisione di completezza e la policy su CLOSED

L'esecutore è verificato da **42 test offline** (`runtime/test_spec_executor.py`) che coprono Mercedes, NVIDIA, genericità (AST scan per nomi source-specifici), description/qualifications reali, completeness/CLOSED, mutation del render, conteggio pagine, e check statico anti-payload-field-name.

**Niente traffico live. Niente database. Niente scheduler.**

## Versione congelata: `source_spec/v0.1`

Il contratto dichiara **esattamente** le feature supportate da questa release. Feature non implementate dal runtime (cursor, page_number, dynamic auth, GraphQL, browser workflows) **non** sono dichiarate e saranno aggiunte in `v0.2` solo quando esercitate da una nuova source reale.

### Supportato in v0.1

| Primitive | Note |
|---|---|
| HTTP method GET / POST | dichiarato in `request.method` |
| URL + static headers + static query + static body | base |
| Templates di request (`request.templates`) | path dotted, value JSON, supporta `{{var}}` |
| Pagination `strategy = offset` | unico supportato; `page_size`, `first_page_value`, `page_param`, `inject.target ∈ {query_param, body_path}` |
| Estrazione campi singoli | `stable_id_path`, `secondary_id_paths`, `title_path`, `department_path`, `organization_path`, `publication_date_path`, `expiration_date_path`, `official_url_path`, `apply_url_path`, `language_path` |
| Date format | `iso_date`, `iso_datetime`, `unix_seconds` |
| Location extraction | `locations.shape ∈ {list_of_strings, list_of_objects}` + `item_template` con placeholders single-brace `{RelKey}`, fallback paths dichiarativi |
| Description extraction | `description.shape ∈ {string, list_of_blocks}`; `list_of_blocks` con `tasks_relative_key` + `qualifications_relative_key` + `join_separator` + `strip_html` |
| Detail request opzionale | `detail.interpolation.target ∈ {query_param, body_path, url_path}`, `detail.description_path` |
| `description_in_catalog` flag | distingue Mercedes-style vs NVIDIA-style |
| Completeness rules tipizzate | `next_offset_ge_total`, `last_page_shorter_than_page_size`, `items_path_empty_after_total`; combinabili |
| `source_of_truth` + `open_closed_authoritative` | decisione dichiarativa per CLOSED |
| Safety policy | `sequential_only`, `min_seconds_between_requests`, `long_pause_every_n_requests`, `max_requests_per_run`, abort su 403/429, retry 5xx |
| Forbidden safety keys | `proxy_rotation`, `ip_rotation`, `user_agent_rotation`, `captcha_bypass`, `anti_bot_evasion` |
| No-arbitrary-code check | rifiuta `eval(`, `exec(`, `compile(`, `__import__`, `getattr(`, `setattr(`, dunder `__` |

### NON supportato in v0.1 (dichiarato nel report, NON nel contratto)

- `paging.strategy ∈ {cursor, page_number}` — non esercitato da fonti reali
- Auth dinamica / token rotation / captcha
- GraphQL
- Source che richiedono browser workflow (cookie stateful, JS rendering)
- Compressione custom / `Content-Encoding` non standard
- Pagination "search-after" cursorless

## Risultato del validatore

```
$ python3 validate_specs.py
[schema] source_spec.schema.json: structural check...
  OK  (14 top-level properties, 8 required)
[schema] job.schema.json: structural check...
  OK  (16 top-level properties, 6 required)
[spec] /Users/.../runtime/sources/mercedes.json
  OK  company_id=mercedes-benz  source_of_truth=full_catalog  description_in_catalog=True
[spec] /Users/.../runtime/sources/nvidia.json
  OK  company_id=nvidia  source_of_truth=full_catalog  description_in_catalog=False

All specs valid.
```

## Risultato dei test

```
$ python3 test_spec_executor.py
... (42 tests, tutti PASS)
Ran 42 tests in 0.037s
OK
```

### Breakdown dei 42 test

| Classe | # | Cosa verifica |
|---|---:|---|
| `GenericityTests` | 2 | AST scan: nessuna menzione di `mercedes` / `nvidia` / `beesite` / `eightfold` / `pcsx` nel codice (incl. commenti). Nessun branch su `company_id ==` / `platform ==`. |
| `ExecutorHardeningTests` | 4 | AST scan: nessun nome di campo payload (DisplayName, PositionFormattedDescription, jobDescription, …) né in codice né in commenti. `paging.strategy` schema è `const: "offset"` (non enum). |
| `SpecValidationTests` | 8 | Entrambe le spec passano il JSON-Schema + i check custom (required sections, paging/completeness consistency, no codice arbitrario, source_of_truth/open_closed_authoritative consistency, paging inject esplicito). |
| `MercedesRequestRenderingTests` | 3 | page 1/2/3 producono FirstItem = 1/51/101. |
| `MercedesExtractionTests` | 3 | stable ID, title, department, organization, locations (`{DisplayName}` risolto!), dates, official URL, apply URL, normalized job conforms to schema. |
| `NvidiaRequestRenderingTests` | 3 | page 1/2/3 producono query.start = 0/10/20. |
| `NvidiaExtractionTests` | 4 | estrazione catalog (no description), detail request con stable_id interpolato, detail response applicata e HTML stripped, schema valido. |
| `CompletenessTests` | 5 | next_offset_ge_total + items_path_empty_after_total passano per Mercedes (total=2798); empty page prima di total ⇒ fail; incomplete ⇒ may_mark_closed=False; complete ⇒ may_mark_closed=True; filtered_catalog ⇒ mai CLOSED. |
| `DescriptionExtractionTests` | 4 | Mercedes estrae **real description e qualifications** dal catalog (no stringhe vuote, no `<p>` sopravvissuti, match su testo reale della fixture). Mercedes `detail_complete=true` dal catalog. NVIDIA `detail_complete=false` dopo catalog; `true` dopo detail merge. |
| `SpecMutationTests` | 2 | rendering di page 1/2/3 + re-render + detail render NON muta lo spec (snapshot JSON identico). |
| `PaginationCountTests` | 4 | Mercedes total=2798 ⇒ **57** richieste totali (56 data pages + 1 empty-after-total probe), offsets esatti [1, 51, …, 2751, 2801]. NVIDIA synthetic total=24 ⇒ 3 requests (no probe). |

## File prodotti

| File | Scopo |
|---|---|
| `runtime/source_spec.schema.json` | Contratto dichiarativo (JSON Schema) v0.1. `paging.strategy` = `const "offset"`. |
| `runtime/job.schema.json` | Modello normalizzato di una vacancy (output dell'estrattore). |
| `runtime/sources/mercedes.json` | Spec Mercedes-Benz — `source_spec/v0.1`, full catalog, authoritative CLOSED, paging `body_path -> SearchParameters.FirstItem`, `description.shape=list_of_blocks` con `tasks_relative_key=Tasks` + `qualifications_relative_key=Qualifications`. |
| `runtime/sources/nvidia.json` | Spec NVIDIA — `source_spec/v0.1`, full catalog, authoritative CLOSED, paging `query_param -> start`, detail request con `jobDescription` HTML. |
| `runtime/validate_specs.py` | Validatore offline delle spec (controlla required sections, paging/completeness consistency, no codice arbitrario, no safety keys vietate). |
| `runtime/spec_executor.py` | **Esecutore source-agnostic**: render request, paging, extraction, normalization, detail, completeness, CLOSED policy. Zero branching source-specifico. Zero payload field names. |
| `runtime/test_spec_executor.py` | 42 test offline che coprono Mercedes, NVIDIA, genericità (AST scan), description/qualifications reali, completeness/CLOSED, mutation, pagination count. |
| `runtime/fixtures/mercedes_catalog_page.json` | Page fixture da `mb/all_jobs_full2.json` (item `mer000484n` reale) con `SearchResultCountAll=2798` (dal probe offline). |
| `runtime/fixtures/nvidia_catalog_page.json` | Page fixture da `NVIDIA/catalog.json` (10 items reali) con `count=2674`. |
| `runtime/fixtures/nvidia_detail.json` | Detail fixture da `NVIDIA/details.jsonl` (item `893397562188` reale). |
| `runtime/SOURCE_SPEC_V0_REPORT.md` | Questo file. |

## Cosa Mercedes e NVIDIA hanno in comune

| Aspetto | Mercedes | NVIDIA |
|---|---|---|
| Endpoint API JSON senza auth | sì | sì |
| Paginazione offset-based con page size fissa | sì (50) | sì (10) |
| Totale dichiarato dal backend (`SearchResultCountAll` / `data.count`) | sì | sì |
| Stable ID per vacancy | `PositionID` (es. `mer00047t6`) | `id` numerico (es. `893397562188`) |
| Title / department / locations nel catalog response | sì | sì |
| URL pubblico della vacancy | fornito (`PositionURI`) | fornito come path; costruito anche da template |
| Apply URL | fornito (`ApplyURI[0]`) | fornito come nested field |
| Publication date | ISO date | unix seconds |
| User-Agent + Accept: application/json sufficienti | sì | sì |
| Nessun cookie / token / captcha per client lenti | sì | sì |
| Throttling su burst rapidi (429/403) | sì | sì |
| Safety circuit breaker (`max_requests_per_run`) applicabile | sì | sì |
| `sequential_only: true` | sì | sì |
| `abort_on_http_403: true` / `abort_on_http_429: true` | sì | sì |

## Cosa differisce

| Aspetto | Mercedes | NVIDIA |
|---|---|---|
| HTTP method | **POST** con body JSON | **GET** con query string |
| Platform/ATS | Beesite (vendor interno) | Eightfold.ai PCSX |
| Auth/headers extra | `Referer` + `Origin` obbligatori | Solo `Accept-Language` opzionale |
| Descrizione nel catalog? | **Sì** (`PositionFormattedDescription.Tasks/Qualifications`) | **No** — richiede detail request |
| Detail endpoint | Non necessario (`description_in_catalog=true`) | `position_details` con `jobDescription` HTML |
| Catalog filtering | **Sì** — la search richiede una `SearchCriteria` (keyword); non c'è modo di chiedere "tutto" senza parametri (la spec usa `SearchCriteria: []` per il full sweep) | **Sì** — ma il campo `query` può essere vuoto = full catalog |
| Lingua | `LanguageCode` nel body | `hl` nella query string |
| Source-of-truth semantics | `full_catalog` | `full_catalog` |
| Date format | ISO date | unix seconds |
| Lingue multiple per stesso PID | sì (DE/EN/HU con `PublicationLanguage.Code`) | no (un solo record per ID) |
| Apply URL | array `ApplyURI[]`, primo = link diretto | nested `positionUserActions.applyAction.applyUrl` (redirect to Workday) |
| Locations format | `list_of_objects` con `item_template = "{DisplayName}"` | `list_of_strings` |
| Description shape | `list_of_blocks` con `tasks_relative_key` + `qualifications_relative_key` | `string` con `strip_html: true` |

## Completeness per Mercedes (total=2798, page_size=50, first=1)

- Data pages: offsets `1, 51, 101, …, 2751` → **56 pagine**
- Empty-after-total probe: offset `2801` → **1 pagina**
- **Totale richieste per authoritative full reconciliation: 57**

Verifica offline (test `PaginationCountTests`):
```
offsets = [1, 51, …, 2751, 2801]  # 57 elementi
total_request_count(spec, 2798) = 57
```

## Risposta alle domande del task

| Item | Risposta |
|---|---|
| Mercedes spec valid | **yes** |
| NVIDIA spec valid | **yes** |
| Custom Python required by Mercedes spec | **no** |
| Custom Python required by NVIDIA spec | **no** |
| Numero di primitive generiche HTTP/pagination/extraction necessarie | 14 blocchi top-level sections, ~30 properties totali; nessuna primitiva per-fonte |
| Live Mercedes/NVIDIA HTTP requests durante questo step | **0** |
| Mercedes full description extracted | **yes** — `Lead the regional digital apps and online platforms portfolio across APAC.` |
| Mercedes qualifications extracted | **yes** — `10+ years in digital product leadership.` |
| NVIDIA hydrated detail complete | **yes** — flip `false → true` dopo detail merge |
| Source-specific payload field names in executor | **0** (codice + commenti + docstringhe, AST scan) |
| Pagination strategies advertised | `offset` |
| Pagination strategies executable | `offset` |
| Spec mutation test | **PASS** (Mercedes + NVIDIA) |
| Mercedes authoritative full reconciliation requests (total=2798) | **57** (56 data + 1 probe) |
| `detail_complete` Mercedes after catalog | **true** |
| `detail_complete` NVIDIA before detail | **false** |
| `detail_complete` NVIDIA after detail | **true** |
| Test totali | **42** (pass: 42, fail: 0) |
| Live HTTP requests | **0** |

## Verdict

**PASS** — il contratto dichiarato da `source_spec/v0.1` coincide esattamente con ciò che `spec_executor.py` esegue realmente:

- il runtime non contiene alcun nome di campo payload (né in codice né in commenti);
- il runtime non contiene alcuna menzione di Mercedes/NVIDIA/Beesite/Eightfold;
- l'unica strategia di paginazione offerta dallo schema (`offset`) è l'unica che il runtime sa eseguire — la coerenza è garantita sia dal `const: "offset"` nel JSON Schema sia dal check `if strategy != "offset": raise` nel codice;
- il rendering non muta mai la spec;
- Mercedes e NVIDIA sono descritte dalla stessa spec syntax (path + template + shape) senza `oneOf` né branching per-fonte;
- description e qualifications sono estratte davvero per Mercedes (catalog) e NVIDIA (detail merge), non lasciate vuote;
- `detail_complete` differenzia correttamente catalog-only vs fully-hydrated.

Quando aggiungeremo una source reale che richiede `cursor` o `page_number`, `dynamic_auth`, `GraphQL`, o `browser_workflow`, estenderemo il contratto a `v0.2` con primitive nuove, esercitate da quella source. Fino ad allora, **NON** dichiariamo supporto per queste feature.

## Caveat noti

- Il runtime sa fare il merge `catalog → detail` per NVIDIA, ma la decisione "quali PIDs richiedono detail" (per evitare di rifare detail su tutti i 2674 record ad ogni sweep) è una preoccupazione del chiamante, non della spec. La spec descrive come fare il render del detail e come applicare la risposta, non quando.
- `preferred_language_codes` è dichiarato ma l'effettiva dedup cross-language (Mercedes: stesso PID in DE/EN/HU) è runtime logic.
- La `safety.min_seconds_between_requests` è dichiarata ma il rispetto effettivo del pacing dipende dal chiamante (il runtime non ha orologio). La spec la documenta; non la forza.
