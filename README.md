# Portugalle Document Management

Local application to:
- Upload documents from your PC.
- Import documents from OneDrive by selecting a synced local folder.
- Translate from Portuguese (`pt`) to English (`en`) and Italian (`it`).
- Save outputs in readable versioned folders (`data/processed/<YYYY-MM-DD_HH-MM-SS>/...`).

## Current Status

This workspace was rebuilt after a file loss event and now includes:
- FastAPI + Jinja2 UI.
- Local file upload.
- OneDrive local-synced-folder import (no App Registration required).
- Azure translation engine with two modes:
  - Sync mode (direct upload, no Blob) for supported formats.
  - Batch + Blob mode for PDF.
- Settings tab to configure Translator + Blob/Batch options.
- Queue and processed output views.
- Progress UI during processing.
- UI language switch (Italian/English) via the app interface.

## Architecture

- Backend/UI: FastAPI + Jinja2.
- Sync translation: Azure Document Translator (`/translator/document:translate`, `api-version=2024-05-01`).
- PDF translation: Azure Document Translator Batch + Azure Blob Storage (`/translator/document/batches`, `api-version=2024-05-01`).
- Local workflow remains unchanged:
  - Input from `data/incoming/input_doc`.
  - Output to `data/processed/<timestamp>/...`.
  - Blob is used only as a temporary bridge for PDF jobs.

## Supported Formats

Sync formats currently routed to Azure sync translation:
- `.txt`, `.tsv`, `.tab`, `.csv`, `.html`, `.htm`, `.mhtml`, `.mht`, `.pptx`, `.xlsx`, `.docx`, `.msg`, `.xlf`

PDF files are routed automatically to the batch + Blob pipeline.

## Requirements

- Windows + PowerShell (tested).
- Python 3.11+ recommended.
- Reachable Azure Translator endpoint (custom domain).
- Azure Translator key.
- Azure Blob Storage account (connection string + source/target containers) for PDF translation.

## Quick Start

1. Set environment variables in PowerShell:

```powershell
$env:AZURE_TRANSLATOR_ENDPOINT = "https://<resource-name>.cognitiveservices.azure.com"
$env:AZURE_TRANSLATOR_KEY = "<translator-key>"
```

2. Start the app:

```powershell
.\run_local.ps1
```

The bootstrap script uses `.venv-app` to reduce issues with stale or broken virtual environments.

App URL: `http://127.0.0.1:8000`

## Environment Variables

- `TRANSLATION_BACKEND=azure_document`
- `AZURE_TRANSLATOR_ENDPOINT=https://<resource-name>.cognitiveservices.azure.com`
- `AZURE_TRANSLATOR_KEY=<key>`
- `AZURE_TRANSLATOR_API_VERSION=2024-05-01` (default)
- `AZURE_TRANSLATOR_TIMEOUT_SEC=600` (optional)
- `AZURE_BLOB_CONNECTION_STRING=<connection_string>` (for PDF)
- `AZURE_BLOB_SOURCE_CONTAINER=<source_container>` (for PDF)
- `AZURE_BLOB_TARGET_CONTAINER=<target_container>` (for PDF)
- `AZURE_TRANSLATOR_BATCH_API_VERSION=2024-05-01` (optional)
- `AZURE_TRANSLATOR_BATCH_TIMEOUT_SEC=1800` (optional)
- `AZURE_TRANSLATOR_BATCH_POLL_SEC=5` (optional)
- `LOCK_TRANSLATOR_SETTINGS=1` (optional, locks settings edits in UI)

## Settings UI

- Available directly in the home page (`Settings` tab).
- Stores UI settings in `data/settings/translator_settings.json`.
- Environment variables always override saved settings.
- Key and Blob connection string fields are password-type in UI.
- If key/connection string fields are left empty, existing saved values are retained.

## OneDrive Import (Mode 2: Local Sync)

- No MSAL/Graph usage.
- No Azure Entra App Registration required.
- App detects OneDrive paths from:
  - Environment (`OneDrive`, `OneDriveConsumer`, `OneDriveCommercial`).
  - Windows Registry (`HKCU\Software\Microsoft\OneDrive`, Personal/Business accounts).
  - Common user paths (`C:/Users/*/OneDrive*`).
- UI shows:
  - Detected OneDrive roots.
  - Selectable synced folders list.
  - Manual path override field.
  - Optional recursive import.
- Imported files are copied into `data/incoming/input_doc` and are then available for translation.

## Production Hardening Notes

If this app is exposed publicly:
- Set `LOCK_TRANSLATOR_SETTINGS=1`.
- Manage secrets only through server-side environment variables or a secret manager.
- Do not expose `data/settings/translator_settings.json` via web server/reverse proxy.
- Use HTTPS and authentication for administrative UI access.

## Project Structure

- `app/main.py`: FastAPI routes and workflow orchestration.
- `app/azure_document_translator.py`: Azure sync translation client.
- `app/azure_pdf_batch_translator.py`: PDF batch pipeline (upload, job start, polling, download).
- `app/format_preserving_translation.py`: routing dispatcher (PDF -> batch; supported formats -> sync).
- `app/onedrive_connector.py`: OneDrive local-synced-folder discovery/import.
- `app/settings_store.py`: settings load/save/effective config handling.
- `app/templates/index.html`: main UI template.
- `app/static/style.css`: styling.
- `run_local.ps1`: local bootstrap/start.

## Operational Notes

- Health check endpoint: `GET /health`.
- If translation fails, verify endpoint/key and Azure quota.
- For PDF translation, verify Blob configuration is complete.
- Blob connection string must be a full connection string (with `AccountName` + `AccountKey`), not a Blob URL.
