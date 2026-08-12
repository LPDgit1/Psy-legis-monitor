# Standalone locale

Fare doppio clic su `open-standalone.cmd` per aprire la dashboard nel browser.
Non richiede Python, Streamlit, Node o una connessione di rete. Il file HTML
contiene l'intero catalogo pubblico disponibile al momento della generazione.

Lo standalone non aggiorna autonomamente le fonti: data e contenuti restano quelli
della snapshot incorporata. I link specifici alle fonti ufficiali sono disponibili
quando il computer e connesso a Internet.

## Rigenerazione

Dalla cartella principale del progetto eseguire:

```text
python standalone/build_standalone.py
```

Lo script incorpora `data/public_documents.json` nel file HTML senza dipendenze
esterne. Per distribuire lo standalone sono sufficienti HTML, README e launcher CMD.
