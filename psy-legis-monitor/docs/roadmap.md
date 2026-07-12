# Roadmap

## Sprint 1: MVP mock/RSS

* Stabilizzare modello normalizzato.
* Eseguire ingest mock.
* Configurare RSS generici.
* Salvare documenti, versioni, eventi e alert.
* Generare report Markdown.

## Sprint 2: connettori nazionali

* Raffinare Gazzetta con testo completo, gestione supplementi e differenze tra serie.
* Implementare Senato.
* Implementare Camera usando portale dati aperti/SPARQL o dataset RDF dopo validazione del mapping.
* Studiare Normattiva per testi consolidati.
* Studiare Normattiva per multivigenza e testi consolidati.

## Sprint 3: connettori regionali

* Implementare Veneto e Lombardia.
* Definire pattern riusabile per BUR, DGR, proposte e piani sociosanitari.
* Estendere progressivamente a tutte le Regioni.

## Sprint 4: classificazione LLM

* Abilitare classificazione opzionale solo con `OPENAI_API_KEY`.
* Validare output JSON con Pydantic.
* Registrare prompt, modello, versione e passaggi rilevanti.
* Aggiungere revisione umana obbligatoria per decisioni operative.

## Sprint 5: dashboard avanzata

* Aggiungere viste per versioni diff.
* Aggiungere workflow di validazione alert.
* Esportare CSV/Markdown/PDF.
* Migliorare filtri e ricerca semantica locale.

## Sprint 6: feedback umano e miglioramento classificatore

* Registrare correzioni degli operatori.
* Misurare falsi positivi e falsi negativi.
* Raffinare pesi YAML e tassonomia.
* Preparare dataset interno per valutazione continua.
