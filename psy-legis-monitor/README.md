# psy-legis-monitor

`psy-legis-monitor` e' un MVP Python per monitorare atti legislativi, normativi e politico-amministrativi italiani rilevanti per la psicologia e per la professione di psicologo.

L'obiettivo non e' cercare solo parole chiave, ma costruire una base di legislative intelligence: dati normalizzati, versionamento, scoring spiegabile, alert motivati e report sintetici per supportare il giudizio umano di un Ordine professionale.

## Requisiti

* Python 3.11+
* SQLite per l'avvio rapido senza configurazione
* PostgreSQL 16 opzionale, consigliato tramite Docker Compose per uso locale persistente
* Docker e Docker Compose opzionali per l'avvio locale completo

## Installazione locale

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Su Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
```

## Avvio rapido su questo PC

I launcher Windows inclusi sono portabili e usano Python disponibile nel `PATH`:

* `launch_dashboard.cmd`
* `stop_dashboard.cmd`

Il batch avvia Streamlit su `http://localhost:8501/`.

## Deploy su Streamlit Community Cloud

Il repository e' pronto per il deploy dalla root.

1. Pubblica la root del repository su GitHub, non includendo file ignorati da `.gitignore`.
2. In Streamlit Community Cloud seleziona come entrypoint:

```text
streamlit_app.py
```

3. Le dipendenze Python sono dichiarate nel `requirements.txt` della root.
4. L'app usa SQLite (`sqlite:///psy_legis_monitor.db`) se `DATABASE_URL` non e' configurato. Il database su Community Cloud e' adatto a demo e uso temporaneo, non a persistenza garantita.
5. Per usare PostgreSQL o un database esterno, imposta nei secrets di Streamlit:

```toml
DATABASE_URL = "postgresql+psycopg://USER:PASSWORD@HOST:PORT/DBNAME"
```

6. La classificazione LLM e' opzionale. Se serve, aggiungi nei secrets:

```toml
OPENAI_API_KEY = "..."
OPENAI_MODEL = "gpt-4.1-mini"
```

Non committare mai `.streamlit/secrets.toml`.

## Avvio con Docker Compose

Docker Compose richiede una password locale per PostgreSQL, impostata fuori dal repository.

Su macOS/Linux:

```bash
export POSTGRES_PASSWORD="scegli-una-password-locale"
docker compose up --build
```

Su Windows PowerShell:

```powershell
$env:POSTGRES_PASSWORD = "scegli-una-password-locale"
docker compose up --build
```

In alternativa puoi usare un file `.env` locale non versionato.

La dashboard Streamlit sara' disponibile su `http://localhost:8501`.

Per caricare i dati mock nel database del container:

```bash
docker compose run --rm app psy-legis ingest-mock
```

## Comandi disponibili

```bash
psy-legis ingest-mock
psy-legis ingest-gazzetta
psy-legis ingest-gazzetta --max-issues 2
psy-legis ingest-rss
psy-legis ingest-pages
psy-legis ingest-camera
psy-legis ingest-senato
psy-legis ingest-normattiva
psy-legis ingest-ministero-salute
psy-legis ingest-agenas
psy-legis ingest-eurlex
psy-legis ingest-regions
psy-legis ingest-priority
psy-legis purge-mock
psy-legis verify-connectors
psy-legis ingest-all
psy-legis score-all
psy-legis generate-report --output reports/weekly_report.md
psy-legis run-dashboard
```

In alternativa:

```bash
python -m app.cli.commands ingest-all
```

## Test

```bash
pytest
```

Controlli di stile:

```bash
ruff check .
black --check .
```

## Fonti reali incluse

`app/config/sources.yml` configura fonti reali e pubbliche:

* Gazzetta Ufficiale - Serie Generale, ultimi 30 giorni.
* Gazzetta Ufficiale - 3a Serie Speciale Regioni, ultimi 30 giorni.
* Camera dei deputati - Dati Camera, via endpoint SPARQL.
* Senato della Repubblica - dati.senato.it, via endpoint SPARQL.
* Normattiva, aggiornamenti in multivigenza e pagina Parlamento delle leggi approvate non ancora pubblicate.
* Ministero della Salute - Norme e atti, connettore HTML; la prova live dalla shell puo' essere bloccata dalla validazione browser Gcore del sito.
* AGENAS, home e aree tematiche istituzionali.
* EUR-Lex, accesso alla Gazzetta ufficiale UE e sezioni normative.
* Regione Lombardia, pagina normativa.
* Regione Veneto, parser per ultime uscite BUR; nella prova live la connessione al portale BUR dalla shell locale non era raggiungibile.
* CNOP - News, feed RSS.
* ENPAP - News page, estrazione HTML dalla home istituzionale.
* ENPAP - News, feed RSS raggiungibile ma attualmente senza item.
* Conferenza Stato-Regioni, pagina notizie/report/odg.
* Garante per la protezione dei dati personali, pagina news/provvedimenti.

Su Windows i connettori web usano `fetch_method: auto`, che ricorre a PowerShell per aggirare limiti TLS/OpenSSL di alcuni runtime Python embedded.

Dettaglio operativo e backlog fonti: `docs/sources.md`.

## Dashboard

La vista iniziale mostra solo atti normativi, proposte di legge, disegni di legge, decreti, regolamenti e bollettini. News, aggiornamenti CNOP/ENPAP, comunicati e informazioni istituzionali restano ricercabili scegliendo esplicitamente la vista `Solo news / aggiornamenti` o `Tutto`.

La tabella principale privilegia titolo, tipo di atto, stato, data, livello, fonte e link diretto alla fonte ufficiale. Score, rilevanza e alert restano disponibili nel dettaglio del documento come strumenti tecnici ausiliari, ma non guidano piu' la griglia principale.

## Limiti dell'MVP

* Alcune fonti istituzionali pubbliche usano pagine dinamiche o protezioni browser: Ministero Salute e BURL Lombardia richiedono un connettore browser/sessione o un endpoint piu' stabile se disponibile.
* Lo scoring e' preliminare e rule-based: propone priorita', non sostituisce la valutazione umana.
* La classificazione LLM e' opzionale e disattivata senza `OPENAI_API_KEY`.
* I connettori HTML generici sono utili per monitorare pagine pubbliche, ma per fonti complesse dovrebbero essere sostituiti da API/feed ufficiali quando disponibili.
* La dashboard supporta triage iniziale, filtri, metriche, dettaglio, alert e report, ma non ancora workflow redazionale completo.

## Roadmap breve

1. Migliorare connettori Ministero Salute e BURL Lombardia con sessione browser o endpoint ufficiali alternativi.
2. Estendere connettori BUR/DGR regionali oltre Veneto e Lombardia.
3. Migliorare deduplica, tipologie atto e canonical URL.
4. Abilitare classificazione LLM con validazione umana.
5. Raffinare dashboard, audit trail e correzione degli alert.
