# Fonti e connettori

Aggiornato: 2026-07-11.

## Connettori attivi

| Connettore | Fonte | URL | Stato |
| --- | --- | --- | --- |
| `gazzetta` | Gazzetta Ufficiale - Serie Generale | `https://www.gazzettaufficiale.it/30giorni/serie_generale` | Verificato |
| `gazzetta` | Gazzetta Ufficiale - 3a Serie Speciale Regioni | `https://www.gazzettaufficiale.it/30giorni/regioni` | Verificato |
| `camera` | Camera dei deputati - Dati Camera SPARQL | `https://dati.camera.it/sparql` | Verificato |
| `senato` | Senato della Repubblica - dati.senato.it SPARQL | `https://dati.senato.it/sparql` | Verificato |
| `normattiva` | Normattiva - aggiornamenti in multivigenza | `https://www.normattiva.it/` | Verificato |
| `normattiva` | Parlamento - leggi approvate non promulgate/pubblicate | `https://www.parlamento.it/leg/ldl_new/v3/sldlelencoddlappnonpub.htm` | Verificato |
| `ministero_salute` | Ministero della Salute - Norme e atti | `https://www.salute.gov.it/new/it/sezione/norme-e-atti/` | Connettore attivo, fetch live bloccato da validazione browser Gcore |
| `agenas` | AGENAS - home e aree tematiche | `https://www.agenas.gov.it/` | Verificato |
| `eurlex` | EUR-Lex - Gazzetta ufficiale UE | `https://eur-lex.europa.eu/homepage.html?locale=it` | Verificato |
| `regione_veneto` | Regione Veneto - BUR | `https://bur.regione.veneto.it/` | Parser attivo e testato; fetch live non raggiungibile dalla shell locale |
| `regione_lombardia` | Regione Lombardia - Normativa | `https://www.regione.lombardia.it/wps/portal/istituzionale/HP/istituzione/Normativa` | Verificato |
| `regione_lombardia` | Regione Lombardia - BURL | `https://www.consultazioniburl.servizirl.it/ConsultazioneBurl/` | Connettore attivo, pagina live lato-client senza link HTML |
| `rss` | CNOP - Consiglio Nazionale Ordine Psicologi | `https://www.psy.it/feed/` | Verificato |
| `rss` | ENPAP - feed RSS | `https://www.enpap.it/feed/` | Raggiungibile, ma oggi senza item |
| `page` | ENPAP - home/news | `https://www.enpap.it/` | Verificato |
| `page` | Conferenza Stato-Regioni | `https://www.statoregioni.it/it/` | Verificato |
| `page` | Garante per la protezione dei dati personali | `https://www.garanteprivacy.it/` | Verificato |

## Verifica tecnica

Audit pulito su `work/psy_legis_monitor_final_audit.db`:

| Fonte | Documenti |
| --- | ---: |
| Garante per la protezione dei dati personali | 30 |
| ENPAP - Ente Nazionale Previdenza e Assistenza Psicologi | 16 |
| Gazzetta Ufficiale - Serie Generale | 16 |
| Gazzetta Ufficiale - 3a Serie Speciale Regioni | 12 |
| CNOP - Consiglio Nazionale Ordine Psicologi | 10 |
| Conferenza Stato-Regioni | 8 |

Totale: 92 documenti reali, 36 alert generati.

Audit fonti prioritarie su `work/psy_legis_monitor_priority_audit.db`:

| Fonte | Documenti |
| --- | ---: |
| AGENAS - Agenzia Nazionale per i Servizi Sanitari Regionali | 40 |
| Camera dei deputati - Dati Camera | 25 |
| EUR-Lex - Gazzetta ufficiale dell'Unione europea | 15 |
| Normattiva - aggiornamenti in multivigenza | 9 |
| Parlamento Italiano - leggi approvate non promulgate o pubblicate | 4 |
| Regione Lombardia - Normativa | 6 |
| Senato della Repubblica - dati.senato.it | 30 |

Totale DB audit fonti prioritarie: 129 documenti normalizzati.

Note live:

* `verify-connectors` prova ogni connettore configurato e stampa `OK`/`ERRORE` con il numero di documenti recuperati per fonte.
* `ingest-priority` ha letto 134 record nel secondo giro, con 6 nuovi, 128 aggiornati e 5 alert.
* `ministero_salute` ha ricevuto una pagina Gcore di validazione browser senza link utili, quindi non ha prodotto record nella shell automatica.
* `regione_veneto` ha parser e test per le ultime uscite BUR, ma la connessione PowerShell al dominio BUR Veneto non era raggiungibile in questa sessione.
* `regione_lombardia` ha prodotto record dalla pagina normativa; il portale BURL ha restituito una shell HTML lato-client senza link.

## Fonti prioritarie sviluppate e sviluppi successivi

1. Normattiva e Open Data Normattiva.
   Stato: connettore attivo per aggiornamenti in multivigenza e leggi approvate ma non ancora pubblicate.
   Prossimo passo: usare Open Data Normattiva per metadati completi, testi consolidati e relazioni tra modifiche.

2. Camera dei deputati - Dati Camera.
   Stato: connettore SPARQL attivo per atti della XIX legislatura.
   Prossimo passo: arricchire status, commissione, firmatari e testi collegati.

3. Senato - dati.senato.it.
   Stato: connettore SPARQL attivo per DDL della XIX legislatura.
   Prossimo passo: integrare testi presentati/approvati e XML Akoma Ntoso dove disponibili.

4. Ministero della Salute.
   Stato: connettore HTML attivo, ma la prova automatica e' bloccata da validazione browser/cookie.
   Prossimo passo: individuare endpoint server-side ufficiale, feed, sitemap, oppure usare sessione browser controllata.

5. Conferenza Stato-Regioni e Conferenza Unificata.
   Rilevanza: accordi, intese, pareri e documenti sanitari ad alta incidenza regionale.
   Connettore consigliato: dedicato per sedute, report, ordine del giorno e atti.

6. BUR e banche dati normative regionali.
   Stato: Veneto e Lombardia avviati; Lombardia normativa verificata, Veneto BUR testato ma non raggiungibile dalla shell live.
   Prossimo passo: aggiungere Lazio, Emilia-Romagna, Piemonte, Toscana, Sicilia, Puglia e parser DGR/leggi regionali.

7. CNOP e Ordini regionali.
   Rilevanza: deontologia, delibere, documenti istituzionali, posizione della professione, formazione.
   Connettore consigliato: feed RSS quando esiste, page connector per news e documenti.

8. ENPAP.
   Rilevanza: previdenza e assistenza degli psicologi, regolamenti, circolari, bandi, chiarimenti fiscali/previdenziali.
   Connettore consigliato: page connector dedicato; il feed RSS e' raggiungibile ma attualmente vuoto.

9. Garante Privacy.
   Rilevanza: dati sanitari, minori, AI, lavoro, ricerca scientifica, segreto professionale e trattamento dati.
   Connettore consigliato: page connector oggi attivo; futuro connettore per provvedimenti e pareri per tema.

10. EUR-Lex.
    Stato: connettore HTML attivo sulla homepage/GU UE.
    Prossimo passo: ricerca CELEX/API o query su Gazzetta UE e atti consolidati.

11. INAIL e Ministero del Lavoro.
    Rilevanza: stress lavoro-correlato, salute e sicurezza, welfare, professionisti e lavoro autonomo.
    Connettore consigliato: page/RSS per news, banche dati normative per documenti tecnici.

## Note operative

* I connettori web usano `fetch_method: auto`; su Windows il fetch passa da PowerShell per evitare errori OpenSSL del runtime Python embedded.
* I connettori `page` sono intentionally conservative: catturano link pubblici rilevanti e li normalizzano come `LegislativeDocument`, ma non sostituiscono un parser dedicato quando esiste una struttura ufficiale piu' stabile.
* `act_type` resta `altro` per fonti non ancora mappate nella tassonomia rigida. Un passo successivo utile e' estendere lo schema con `accordo_intesa`, `provvedimento_autorita`, `notizia_istituzionale`, `circolare` e `linea_guida`.
