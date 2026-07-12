# Architettura

## Architettura logica

`psy-legis-monitor` è diviso in livelli:

* `connectors`: raccolgono dati da fonti specifiche e li mappano nel modello normalizzato.
* `core`: contiene modelli Pydantic, ORM, hashing, scoring, tassonomia, change detection e classificazione opzionale.
* `services`: coordina ingestione, alert, report ed export.
* `ui`: dashboard Streamlit.
* `cli`: comandi operativi.

Questa separazione evita che le regole di una fonte entrino nei servizi generali.

## Flusso ingestione

1. Un connector produce una lista di `LegislativeDocument`.
2. Il servizio `ingest` calcola `document_key` e hash del testo normalizzato.
3. Il database salva il documento se è nuovo.
4. Se il testo cambia, viene creata una nuova `DocumentVersion`.
5. Se cambiano stato, metadata o URL, vengono registrati `LegislativeEvent`.
6. Ogni documento viene sottoposto a scoring e tassonomia.
7. Se necessario viene generato un alert spiegabile.

## Connettore Gazzetta

`GazzettaConnector` usa gli elenchi ufficiali degli ultimi 30 giorni configurati in `sources.yml`.

Flusso:

1. Scarica la pagina elenco della serie configurata.
2. Estrae i link alle singole Gazzette pubblicate.
3. Entra nella pagina sommario della Gazzetta.
4. Estrae i link ai singoli atti, l'identificativo redazionale, titolo e sintesi.
5. Normalizza ogni atto in `LegislativeDocument`.

Il testo completo del singolo atto può essere abilitato con `--fetch-act-text`, ma per l'MVP resta opzionale per evitare carico inutile sulla fonte ufficiale.

## Flusso scoring

`keywords.yml` definisce categorie, pesi e soglie. `score_document()` cerca termini e frasi nel titolo, nel summary e nel testo. Il risultato contiene punteggio totale, punteggi per categoria, parole trovate e classe preliminare.

## Flusso alert

`alerting.py` usa scoring e tassonomia:

* rosso: impatto diretto su professione, competenze o servizi psicologici;
* arancione: rilevanza indiretta importante;
* blu: scenario strategico, tecnologia, dati sanitari o monitoraggio.

## Flusso report

`reports.py` genera Markdown con sintesi esecutiva, nuovi atti, modifiche, alert per colore, candidati falsi positivi, azioni suggerite e link ufficiali.
