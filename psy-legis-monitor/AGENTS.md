# AGENTS.md

Istruzioni per futuri interventi di Codex su `psy-legis-monitor`.

* Mantenere l'architettura modulare.
* Non inserire logica specifica delle fonti dentro i servizi core.
* Usare sempre modelli Pydantic per validare dati provenienti da fonti esterne.
* Scrivere test per ogni nuova funzione.
* Non rompere la compatibilità dei file YAML.
* Separare dati pubblici da annotazioni interne.
* Non inviare dati a LLM esterni se la funzione non è esplicitamente abilitata.
* Documentare ogni nuovo connettore.
* Trattare le fonti ufficiali come fonti primarie.
* Registrare sempre URL e data di accesso/aggiornamento.

Linee operative:

* I connettori devono restituire solo `LegislativeDocument`.
* I servizi di ingestione, scoring, alerting e report non devono conoscere i dettagli tecnici delle fonti.
* Ogni alert deve restare spiegabile tramite categorie, parole chiave, aree tematiche o output LLM validato.
* Le classificazioni automatiche devono essere considerate proposte modificabili da un operatore umano.

