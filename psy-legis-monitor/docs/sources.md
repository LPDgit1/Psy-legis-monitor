# Fonti e connettori

Aggiornato: 2026-08-12.

## Fonti nazionali, europee e istituzionali

| Connettore | Fonte | Accesso | Esito live 2026-08-12 |
| --- | --- | --- | --- |
| `gazzetta` | Gazzetta Ufficiale, Serie Generale | HTML ufficiale | HTTP 200 |
| `gazzetta` | Gazzetta Ufficiale, 3a Serie Speciale Regioni | HTML ufficiale | HTTP 200 |
| `camera` | Camera dei deputati | Snapshot SPARQL validata | 200 atti; snapshot GitHub 2026-08-12 |
| `senato` | Senato della Repubblica | SPARQL `dati.senato.it` | Endpoint HTTP 200 |
| `normattiva` | Normattiva | HTML ufficiale | HTTP 200 |
| `normattiva` | Parlamento, leggi approvate non pubblicate | HTML ufficiale | HTTP 200 |
| `ministero_salute` | Ministero Salute, Norme e atti | HTML ufficiale | HTTP 200 |
| `ministero_salute` | Trova Norme Salute | HTML di ricerca ufficiale | HTTP 200 |
| `agenas` | AGENAS | HTML ufficiale | HTTP 200 |
| `eurlex` | EUR-Lex, legislazione Parlamento/Consiglio | RSS ufficiale `rssId=162` | HTTP 200 XML |
| `eurlex` | EUR-Lex, atti GU serie L | RSS ufficiale `rssId=165` | HTTP 200 XML |
| `rss` | CNOP | RSS | HTTP 200 XML |
| `rss` / `page` | ENPAP | RSS e HTML | HTTP 200 |
| `page` | Conferenza Stato-Regioni | HTML ufficiale | HTTP 200 |
| `page` | Garante Privacy | HTML ufficiale | HTTP 200 |

La homepage EUR-Lex ha restituito `202` con corpo vuoto durante la verifica. Per questo il
connettore usa i feed RSS indicati dalla documentazione EUR-Lex come modalità stabile di
aggiornamento, senza credenziali.

## Bollettini ufficiali regionali

Il connettore `regional_burs` valida un registro di 20 Regioni e isola gli errori: il
fallimento di un portale non interrompe gli altri. `html_pdf` indica navigazione limitata
indice-fascicolo e lettura del primo PDF entro 15 MB; `html` usa le pagine che espongono
atti o dettagli consultabili; `veneto` usa il parser storico dedicato.

| Regione | Fonte ufficiale | Adapter | Esito live 2026-08-12 |
| --- | --- | --- | --- |
| Abruzzo | `https://bura.regione.abruzzo.it/` | `html_pdf` | HTTP 200 |
| Basilicata | `https://burweb.regione.basilicata.it/bur/ricercaBollettini.zul` | `html_pdf` | HTTP 200, app ZK |
| Calabria | `https://burc.regione.calabria.it/` | `html_pdf` | HTTP 200 |
| Campania | `https://burc.regione.campania.it/eBurcWeb/publicContent/home/index.iface` | `html_pdf` | HTTP 200, app JSF |
| Emilia-Romagna | `https://bur.regione.emilia-romagna.it/anno` | `html_pdf` | HTTP 200 |
| Friuli Venezia Giulia | `https://bur.regione.fvg.it/newbur/visionaBUR` | `html_pdf` | HTTP 200 |
| Lazio | `https://www.regione.lazio.it/bur?vw=ultimibur` | `html_pdf` | HTTP 200 |
| Liguria | `https://www.burl.it/` | `html_pdf` | HTTP 200 |
| Lombardia | `https://www.consultazioniburl.servizirl.it/ConsultazioneBurl/` | `html_pdf` | HTTP 200, shell JS |
| Marche | `https://www.regione.marche.it/Entra-in-Regione/BUR` | `html_pdf` | HTTP 200 |
| Molise | `https://www.regione.molise.it/flex/cm/pages/ServeBLOB.php/L/IT/IDPagina/18` | `html_pdf` | HTTP 200 |
| Piemonte | `https://www.regione.piemonte.it/governo/bollettino/registra.htm` | `html_pdf` | HTTP 200 |
| Puglia | `https://burp.regione.puglia.it/bollettini` | `html` | HTTP 200 |
| Sardegna | `https://buras.regione.sardegna.it/` | `html` | HTTP 200 |
| Sicilia | `https://www.gursonline.regione.sicilia.it/` | `html_pdf` | HTTP 200 |
| Toscana | `https://www.regione.toscana.it/burt` | `html_pdf` | HTTP 200 |
| Trentino-Alto Adige | `https://bollettino.regione.taa.it/` | `html_pdf` | HTTP 200 |
| Umbria | `https://bur.regione.umbria.it/` | `html_pdf` | HTTP 200 |
| Valle d'Aosta | `https://www.regione.vda.it/affari_legislativi/bollettino_ufficiale/default_i.asp` | `html_pdf` | HTTP 200 |
| Veneto | `https://bur.regione.veneto.it/BurvServices/pubblica/HomeBollettini.aspx` | `veneto` | HTTP 200 |

Per le leggi regionali restano attive anche la Gazzetta Ufficiale 3a Serie Speciale e le
banche dati normative regionali gia configurate. Sono coperture complementari importanti
per i portali BUR lato-client che non espongono titoli o URL nel primo HTML.

## Regole di pertinenza

Gli atti sono inclusi se presentano un riferimento diretto a psicologia, psicoterapia,
servizi psicologici o salute mentale, oppure almeno due contesti coerenti tra sanita,
minori/famiglia, disabilita, violenza, digitale sanitario e presa in carico, con un
segnale concreto di servizio, assistenza, salute o vulnerabilita. La provenienza da una
ricerca per parola chiave non basta piu da sola.

Per i BUR il controllo viene applicato al titolo e a una finestra iniziale dell'atto,
non all'intero PDF: questo evita che un acronimo o una parola isolata in un bollettino
molto lungo promuova il documento. Sono inoltre esclusi, salvo un riferimento
psicologico diretto, i contenuti su istituti agrari/enologici e sul comparto
vitivinicolo.

Sono esclusi, in assenza di un segnale psicologico diretto, temi veterinari, fauna e
allevamenti, fitoterapici/integratori, sicurezza alimentare ed esportazioni alimentari.
Anche la generica salute digitale dei minori e la dipendenza da piattaforme restano fuori
dalla vista ordinaria se non attribuiscono un ruolo a psicologi o servizi pertinenti.

Le stesse esclusioni sono applicate alla vista, così i falsi positivi gia presenti nel
database non ricompaiono dopo il deployment.

## Verifica

* `python -m app.cli.commands verify-connectors` verifica i connettori e stampa l'esito per Regione.
* `python -m app.cli.commands check-camera-snapshot --max-age-hours 168` controlla la freschezza Camera.
* La verifica automatica distingue una fonte raggiungibile senza atti pertinenti da un errore tecnico.
* Su Windows `fetch_method: auto` usa PowerShell; su Streamlit Cloud usa HTTP Python.
