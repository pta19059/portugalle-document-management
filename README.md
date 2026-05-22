# Portugalle Document Management (Locale - Ripristino)

App locale per:
- Caricare documenti dal PC.
- Importare documenti da OneDrive specificando una cartella.
- Importare file OneDrive tramite pulsante di selezione cartella (senza digitare path).
- Rilevare automaticamente le cartelle OneDrive locali e mostrarle come suggerimenti in UI.
- Tradurre da portoghese (`pt`) a inglese (`en`) e italiano (`it`).
- Salvare output in cartelle versionate leggibili (`data/processed/<YYYY-MM-DD_HH-MM-SS>/...`).

## Stato ripristino

Questa versione e stata ricostruita da zero dopo perdita file workspace.

Componenti inclusi:
- UI FastAPI + Jinja2.
- Caricamento locale file.
- Processo traduzione con output per lingua target.
- Motore Azure con due modalita:
	- Sync (upload diretto, senza Blob) per formati supportati.
	- Batch + Blob per PDF.
- Tab `Settings` in UI per configurare endpoint/key/api-version/timeout e parametri Blob/Batch.
- Sezione "Aiuto rapido" direttamente in app con summary su motori, flusso e limiti operativi.
- Barra di avanzamento visuale durante la fase di processing (stato attivo finche la richiesta non termina).
- Theme UI futuristico con font dedicati.
- Troncamento dinamico nomi file in coda con estensione sempre visibile.
- Banner `message`/`error` transitori: dopo il primo render la URL viene pulita automaticamente dai query params per evitare errori stale a refresh.
- Lista "File Processati" pulita: i file tecnici di test in cartelle interne con prefisso `_` non vengono mostrati in UI.
- Nei risultati utente vengono mostrati solo i file finali `translated_*`.

Componenti temporaneamente semplificati:
- Per formati non testuali complessi (`docx`, `pptx`, `xlsx`, immagini) il comportamento di default e copia con estensione preservata.

Import OneDrive implementato in modalita locale (senza App Registration):
- La route usa una cartella OneDrive gia sincronizzata sul PC.
- L'import copia i file supportati in `data/incoming/input_doc` (con supporto ricorsivo opzionale).
- Non usa MSAL/Graph e non richiede configurazione Azure Entra ID.
- In UI vengono mostrate automaticamente le radici OneDrive rilevate e un elenco di cartelle sincronizzate selezionabili per compilare il path di import.
- Il rilevamento usa env (`OneDrive`/`OneDriveConsumer`/`OneDriveCommercial`), registry Windows (`HKCU\\Software\\Microsoft\\OneDrive`) e path utente comuni (`C:/Users/*/OneDrive*`).
- Flusso consigliato: seleziona una cartella dal menu in UI (o inserisci il path manualmente), poi premi l'unico pulsante `Importa cartella selezionata`.
- Checkbox `Import ricorsivo (sottocartelle)`: se attivo, include anche i file nelle sottocartelle della cartella OneDrive scelta.

## Architettura

- Backend/UI: `FastAPI` + `Jinja2`.
- Traduzione documenti sync: `Azure Document Translator` (`/translator/document:translate`, `api-version=2024-05-01`).
- Traduzione PDF: `Azure Document Translator Batch` con `Azure Blob Storage` (`/translator/document/batches`, `api-version=2024-05-01`).
- Modalita operativa locale invariata: input/output restano nelle cartelle locali; Blob viene usato come ponte temporaneo solo per PDF.
- Formati sync supportati in app: `.txt`, `.tsv`, `.tab`, `.csv`, `.html`, `.htm`, `.mhtml`, `.mht`, `.pptx`, `.xlsx`, `.docx`, `.msg`, `.xlf`.
- I file PDF passano automaticamente dal flusso batch con Blob (se configurato).
- Layout UI: tema neon/cyan, font `Orbitron` + `Space Grotesk`.

## Requisiti

- Windows + PowerShell (testato).
- Python 3.11+ consigliato.
- Endpoint Azure Translator (custom domain) raggiungibile.
- Credenziali Azure Translator (Key) disponibili.
- Storage account Blob (connection string + source/target container) se vuoi tradurre PDF.

## Installazione rapida

1. Imposta variabili ambiente (sessione PowerShell):

```powershell
$env:AZURE_TRANSLATOR_ENDPOINT = "https://<resource-name>.cognitiveservices.azure.com"
$env:AZURE_TRANSLATOR_KEY = "<translator-key>"
```

2. Avvia app:

```powershell
.\run_local.ps1
```

Lo script usa un ambiente dedicato `.venv-app` per evitare lock su vecchi ambienti corrotti.

App disponibile su `http://127.0.0.1:8000`.

## Variabili ambiente

- `TRANSLATION_BACKEND=azure_document`
- `AZURE_TRANSLATOR_ENDPOINT=https://<resource-name>.cognitiveservices.azure.com`
- `AZURE_TRANSLATOR_KEY=<key>`
- `AZURE_TRANSLATOR_API_VERSION=2024-05-01` (default)
- `AZURE_TRANSLATOR_TIMEOUT_SEC=600` (opzionale)
- `AZURE_BLOB_CONNECTION_STRING=<connection_string>` (per PDF)
- `AZURE_BLOB_SOURCE_CONTAINER=<container_source>` (per PDF)
- `AZURE_BLOB_TARGET_CONTAINER=<container_target>` (per PDF)
- `AZURE_TRANSLATOR_BATCH_API_VERSION=2024-05-01` (opzionale)
- `AZURE_TRANSLATOR_BATCH_TIMEOUT_SEC=1800` (opzionale)
- `AZURE_TRANSLATOR_BATCH_POLL_SEC=5` (opzionale)
- `LOCK_TRANSLATOR_SETTINGS=1` (opzionale, blocca modifiche da tab Settings)

Nota su Azure Document Translation:
- Per PDF la app usa batch asincrono con Blob e polling stato job.
- Per formati sync la app usa upload diretto senza Blob.
- La traduzione resta orchestrata localmente: input da `data/incoming`, output in `data/processed` con la stessa struttura cartelle.
- Se Blob non e configurato e provi a tradurre PDF, l'app mostra errore esplicito di configurazione.
- `blob_connection_string` deve essere la connection string completa dello Storage Account (con `AccountName` e `AccountKey`), non l'URL `https://...blob.core.windows.net/`.

## Settings in UI

- Tab `Settings` disponibile in home page per configurare Azure Translator senza toccare codice.
- In tab `Settings` puoi configurare anche Blob source/target e parametri Batch per PDF.
- Le impostazioni UI sono salvate localmente in `data/settings/translator_settings.json`.
- Le variabili ambiente hanno priorita sulle impostazioni salvate.
- I campi key e connection string in UI sono di tipo password; se lasciati vuoti mantengono il valore gia presente.

## Se app diventera pubblica

- Impostare `LOCK_TRANSLATOR_SETTINGS=1` per disabilitare la modifica credenziali da UI.
- Gestire endpoint e key solo tramite variabili ambiente lato server (o secret manager).
- Evitare di esporre `data/settings/translator_settings.json` via web server/reverse proxy.
- Preferire HTTPS e autenticazione per accesso alla UI amministrativa.

## Struttura progetto

- `app/main.py`: routing FastAPI e orchestrazione workflow.
- `app/azure_document_translator.py`: client Azure Document Translator sync (multipart upload locale).
- `app/azure_pdf_batch_translator.py`: pipeline PDF via Azure Batch + Blob (upload, start job, polling, download).
- `app/format_preserving_translation.py`: dispatcher: PDF -> batch Blob, altri formati supportati -> sync.
- `app/translator.py`: eccezione `TranslationError` condivisa.
- `app/onedrive_connector.py`: import da cartella OneDrive locale sincronizzata (mode 2, senza App Registration).
- `app/templates/index.html`: UI principale.
- `app/static/style.css`: stile futuristico responsive.
- `run_local.ps1`: bootstrap env e avvio app.

## Note operative

- In caso di errore traduzione: verificare endpoint/key Azure e quota disponibile.
- Le richieste usano endpoint custom domain della risorsa Translator.
- Route health check: `GET /health`.
- Dati input: `data/incoming/input_doc`.
- Dati output: `data/processed/<timestamp>/`.
- Import OneDrive (modalita 2): nel form inserisci il path locale OneDrive, ad esempio `C:/Users/<utente>/OneDrive/Documenti/Contratti`.
