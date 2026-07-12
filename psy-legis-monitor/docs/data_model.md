# Modello dati

## LegislativeDocument

`LegislativeDocument` è il contratto normalizzato tra connettori e sistema. Include fonte, tipo fonte, livello, regione, tipo atto, identificativo, titolo, date, stato, URL, testo e metadata liberi.

## Tabelle principali

* `documents`: snapshot corrente del documento normalizzato.
* `document_versions`: versioni testuali basate su hash del testo normalizzato.
* `legislative_events`: eventi di novità o modifica.
* `relevance_assessments`: scoring e classificazioni preliminari.
* `alerts`: alert operativi, con livello, motivazione e azione suggerita.
* `weekly_reports`: report Markdown generati.

## Logica di versionamento

Il sistema calcola un hash SHA-256 sul testo normalizzato. Se un documento già noto arriva con hash diverso, viene creata una nuova `DocumentVersion` e un evento `text_changed`.

La chiave documento usa `source + identifier` quando l'identificativo ufficiale esiste. Se manca, usa `source + url`; in ultima istanza usa fonte, titolo e data di pubblicazione. Questa scelta permette di rilevare cambi di URL quando l'identificativo ufficiale è stabile.

## Metadata

Il campo `metadata` conserva informazioni specifiche della fonte: commissione, firmatari, legislatura, numero BUR, serie Gazzetta, data di accesso e altri attributi verificabili.

