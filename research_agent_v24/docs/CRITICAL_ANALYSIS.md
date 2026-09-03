# Analisi critica del progetto

Data: 2026-08-31

## Valutazione attuale

L'MVP e' ora verificato end-to-end per un singolo operatore locale. I precedenti P0/P1 sono stati
chiusi: registry e rollout sono stati corretti in modo versionato, la coorte rappresentativa da 100
ha superato il gate, il benchmark e' salito a 212 casi, seniority/geografia e alias aziendali sono
stati rafforzati, il dashboard rende spiegabili review e failure, e backup/recovery sono provati.

L'architettura resta coerente con il problema: separa universo aziende, registry dei portali e
osservazioni delle vacancy; evita richieste per master row; mantiene import, filtri, dedup e lifecycle
deterministici e auditabili. La copertura non va pero' confusa con completezza universale.

## P0/P1 chiusi

- **Igiene registry e scala:** correzioni versionate, circuit breaker, cooldown e coorte 100 PASS con
  8% failure, zero retry e zero `429`.
- **Tassonomia:** 212 casi stratificati; cyber 100%, seniority 98,1%, geography 100% e decisione finale
  100%, sopra il gate del 95%.
- **Seniority/geografia:** parsing conservativo di esperienza e livelli ordinali; distinzione tra
  paese strutturato sconosciuto e fuori scope noto.
- **Lifecycle del fallback:** resta intenzionalmente `incomplete` e non puo' chiudere vacancy.
- **Company resolution:** alias con provenance e stato; il fuzzy matching propone soltanto.
- **Operativita':** dashboard spiegabile con tutte le analytics minime del handover, CI offline,
  retention, backup e recovery eseguiti.

## Aree di crescita P2

### Copertura strutturata

I 123 route strutturati consentono snapshot piu' affidabili, ma 369 portali scansionabili usano ancora
il fallback HTML incompleto. La crescita utile e' aggiungere adapter solo dove esiste un contratto
pubblico osservato, con fixture sanitizzata, test e canary limitato. Il browser non va usato per
trasformare un access denial in un successo.

### Risoluzione aziende

Wave 6 ha risolto 15 dei 100 cluster prioritizzati senza forzare gli altri 85. Restano 11.209 cluster
non mappati. Le prossime wave devono mantenere score riproducibile, endpoint ufficiali ed evidenza;
acronimi, controllate e omonimie ambigue vanno differiti.

### Rappresentativita' delle vacancy

Il database corrente contiene 5.789 source job attivi e 48 canonical job attivi, tutti `REVIEW`.
Questo dimostra un pipeline prudente, non un alto yield di vacancy incluse. Conviene osservare nuovi
casi reali, ampliare il benchmark senza cambiare silenziosamente le label e misurare precision/recall
su distribuzioni temporali diverse.

### Fonte LinkedIn manuale

Import, idempotenza e dedup cross-source sono testati, ma non era disponibile un CSV di produzione
revisionato. Quando l'operatore lo fornira', si potranno misurare official-only, LinkedIn-only e
duplicati cross-source. Login automation, scraping autenticato e bypass anti-bot restano esclusi.

### Evoluzione operativa solo su trigger

SQLite e avvio manuale sono adeguati a volume e concorrenza misurati. Migrazioni formali servono prima
del primo cambiamento non additivo; scheduler o database diverso servono solo con evidenza di carico,
concorrenza o run mancati. Introdurli ora aumenterebbe la superficie operativa senza risolvere un
problema osservato.

## Miglioramenti da evitare

- scraping LinkedIn autenticato o bypass anti-bot;
- Playwright come default o per aggirare protezioni;
- richiesta per ogni master row o scansione `--all` non presidiata;
- fuzzy company mapping automatico;
- classificazione LLM non deterministica nel path di inclusione;
- cloud, microservizi o Postgres senza bisogno misurato;
- allargamento dello scope a people research, CV fit, SWE generico, senior o Middle East.
