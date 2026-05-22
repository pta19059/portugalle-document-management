from __future__ import annotations

from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .format_preserving_translation import translate_file_preserve_format
from .onedrive_connector import (
    OneDriveImportError,
    discover_local_onedrive_folders,
    discover_local_onedrive_roots,
    import_folder_from_onedrive,
)
from .settings_store import (
    get_effective_translator_config,
    is_translator_settings_locked,
    load_translator_settings,
    redact_connection_string,
    redact_key,
    save_translator_settings,
)
from .translator import TranslationError


BASE_DIR = Path(__file__).resolve().parents[1]
INCOMING_DIR = BASE_DIR / "data" / "incoming"
DEFAULT_INCOMING_SUBDIR = INCOMING_DIR / "input_doc"
PROCESSED_DIR = BASE_DIR / "data" / "processed"

for path in (DEFAULT_INCOMING_SUBDIR, PROCESSED_DIR):
    path.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Portugalle Document Management")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


UI_TEXTS = {
    "it": {
        "hero_eyebrow": "Local AI Workflow",
        "hero_subtitle": "Pipeline locale per import e traduzione PT->EN/IT con Azure Document Translator (sync + PDF batch via Blob).",
        "tab_workflow": "Workflow",
        "tab_settings": "Settings",
        "help_summary": "Aiuto rapido: come funziona l'app",
        "help_intro": "L'app gira in locale e usa un unico motore cloud: Azure Document Translator in modalita sincrona con upload diretto del file (senza Blob Storage).",
        "help_engine": "Motore unico:",
        "help_engine_desc": "Azure Document Translator per i formati supportati in modalita sync.",
        "help_no_blob": "Nessun Blob richiesto:",
        "help_no_blob_desc": "il file viene inviato direttamente all'endpoint sync.",
        "help_pdf": "PDF con Azure:",
        "help_pdf_desc": "disponibili via modalita batch usando Azure Blob Storage.",
        "help_languages": "Lingue principali:",
        "help_languages_desc": "sorgente PT, target EN/IT.",
        "help_output": "Output:",
        "help_output_desc": "file tradotti in",
        "help_onedrive": "OneDrive:",
        "help_onedrive_desc": "import da cartella locale gia sincronizzata, senza App Registration.",
        "help_hint": "Configura AZURE_TRANSLATOR_ENDPOINT e AZURE_TRANSLATOR_KEY. Per PDF configura anche Blob nella tab Settings.",
        "sec_upload_title": "1) Carica Documenti Locali",
        "upload_label": "Seleziona uno o piu file",
        "upload_button": "Carica",
        "sec_onedrive_title": "2) Import da OneDrive (cartella locale sincronizzata)",
        "onedrive_roots": "Radici OneDrive rilevate sul PC",
        "onedrive_select": "Seleziona cartella OneDrive sincronizzata",
        "onedrive_select_placeholder": "-- seleziona una cartella --",
        "onedrive_path": "Path cartella OneDrive (es. Documenti/Contratti)",
        "onedrive_path_placeholder": "C:/Users/<utente>/OneDrive/Documenti/Contratti",
        "onedrive_recursive": "Import ricorsivo (sottocartelle)",
        "onedrive_recursive_desc": "Se attivo, importa anche i file presenti nelle sottocartelle della cartella selezionata.",
        "onedrive_import": "Importa cartella selezionata",
        "onedrive_none": "Nessuna cartella OneDrive rilevata automaticamente. Inserisci il path manualmente.",
        "sec_translate_title": "3) Traduce PT -> EN/IT",
        "source_lang": "Lingua sorgente",
        "queue_files": "File in coda",
        "queue_empty": "Nessun file presente in data/incoming.",
        "target_langs": "Lingue target",
        "start_translate": "Avvia traduzione",
        "processing": "Elaborazione in corso, attendi...",
        "processed_files": "File Processati",
        "no_output": "Nessun output ancora generato.",
        "settings_title": "Settings - Azure Document Translator",
        "settings_hint": "Configura endpoint e credenziali per la traduzione documenti.",
        "settings_locked": "Modalita bloccata attiva: modifica via UI disabilitata.",
        "settings_state": "Stato configurazione attiva:",
        "settings_blob_state": "Stato Blob per PDF batch:",
        "settings_source": "Sorgente configurazione attiva:",
        "complete": "completa",
        "incomplete": "incompleta",
        "blob_complete": "completo",
        "blob_incomplete": "incompleto",
        "key_saved": "Key salvata (masked):",
        "blob_saved": "Blob connection string (masked):",
        "endpoint": "Azure Translator Endpoint",
        "endpoint_placeholder": "https://<resource-name>.cognitiveservices.azure.com",
        "key": "Azure Translator Key",
        "key_placeholder": "Lascia vuoto per mantenere la key gia salvata",
        "api_version": "API Version",
        "timeout": "Timeout (secondi)",
        "blob_conn": "Blob Connection String (per PDF batch)",
        "blob_conn_placeholder": "DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;EndpointSuffix=core.windows.net",
        "blob_source": "Blob Source Container (per PDF batch)",
        "blob_target": "Blob Target Container (per PDF batch)",
        "batch_api": "Batch API Version (per PDF)",
        "batch_timeout": "Batch Timeout (secondi)",
        "batch_poll": "Batch Poll Interval (secondi)",
        "save_settings": "Salva impostazioni",
        "public_hint": "Se l'app verra resa pubblica, imposta LOCK_TRANSLATOR_SETTINGS=1 e usa solo variabili ambiente lato server.",
        "lang_label": "Lingua",
        "kpi_queue": "in coda",
        "kpi_output": "output",
    },
    "en": {
        "hero_eyebrow": "Local AI Workflow",
        "hero_subtitle": "Local pipeline for PT->EN/IT import and translation with Azure Document Translator (sync + PDF batch via Blob).",
        "tab_workflow": "Workflow",
        "tab_settings": "Settings",
        "help_summary": "Quick help: how the app works",
        "help_intro": "The app runs locally and uses one cloud engine: Azure Document Translator in synchronous mode with direct file upload (without Blob Storage).",
        "help_engine": "Single engine:",
        "help_engine_desc": "Azure Document Translator for supported sync formats.",
        "help_no_blob": "No Blob required:",
        "help_no_blob_desc": "the file is sent directly to the sync endpoint.",
        "help_pdf": "PDF with Azure:",
        "help_pdf_desc": "available through batch mode using Azure Blob Storage.",
        "help_languages": "Main languages:",
        "help_languages_desc": "source PT, target EN/IT.",
        "help_output": "Output:",
        "help_output_desc": "translated files in",
        "help_onedrive": "OneDrive:",
        "help_onedrive_desc": "import from a local synced folder, no App Registration required.",
        "help_hint": "Configure AZURE_TRANSLATOR_ENDPOINT and AZURE_TRANSLATOR_KEY. For PDFs configure Blob as well in the Settings tab.",
        "sec_upload_title": "1) Upload Local Documents",
        "upload_label": "Select one or more files",
        "upload_button": "Upload",
        "sec_onedrive_title": "2) Import from OneDrive (local synced folder)",
        "onedrive_roots": "OneDrive roots detected on this PC",
        "onedrive_select": "Select synced OneDrive folder",
        "onedrive_select_placeholder": "-- select a folder --",
        "onedrive_path": "OneDrive folder path (example: Documents/Contracts)",
        "onedrive_path_placeholder": "C:/Users/<user>/OneDrive/Documents/Contracts",
        "onedrive_recursive": "Recursive import (subfolders)",
        "onedrive_recursive_desc": "If enabled, files from subfolders of the selected folder are imported too.",
        "onedrive_import": "Import selected folder",
        "onedrive_none": "No OneDrive folder was detected automatically. Enter the path manually.",
        "sec_translate_title": "3) Translate PT -> EN/IT",
        "source_lang": "Source language",
        "queue_files": "Queued files",
        "queue_empty": "No files found in data/incoming.",
        "target_langs": "Target languages",
        "start_translate": "Start translation",
        "processing": "Processing, please wait...",
        "processed_files": "Processed files",
        "no_output": "No output generated yet.",
        "settings_title": "Settings - Azure Document Translator",
        "settings_hint": "Configure endpoint and credentials for document translation.",
        "settings_locked": "Locked mode is active: UI changes are disabled.",
        "settings_state": "Active configuration state:",
        "settings_blob_state": "Blob state for PDF batch:",
        "settings_source": "Active configuration source:",
        "complete": "complete",
        "incomplete": "incomplete",
        "blob_complete": "complete",
        "blob_incomplete": "incomplete",
        "key_saved": "Saved key (masked):",
        "blob_saved": "Blob connection string (masked):",
        "endpoint": "Azure Translator Endpoint",
        "endpoint_placeholder": "https://<resource-name>.cognitiveservices.azure.com",
        "key": "Azure Translator Key",
        "key_placeholder": "Leave empty to keep the currently saved key",
        "api_version": "API Version",
        "timeout": "Timeout (seconds)",
        "blob_conn": "Blob Connection String (for PDF batch)",
        "blob_conn_placeholder": "DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;EndpointSuffix=core.windows.net",
        "blob_source": "Blob Source Container (for PDF batch)",
        "blob_target": "Blob Target Container (for PDF batch)",
        "batch_api": "Batch API Version (for PDF)",
        "batch_timeout": "Batch Timeout (seconds)",
        "batch_poll": "Batch Poll Interval (seconds)",
        "save_settings": "Save settings",
        "public_hint": "If this app becomes public, set LOCK_TRANSLATOR_SETTINGS=1 and use only server-side environment variables.",
        "lang_label": "Language",
        "kpi_queue": "queued",
        "kpi_output": "output",
    },
}


RUNTIME_TEXTS = {
    "it": {
        "invalid_upload": "Nessun file valido selezionato",
        "uploaded_files": "Caricati {count} file",
        "onedrive_import_error": "Errore import OneDrive: {error}",
        "onedrive_imported": "Importati {count} file da OneDrive",
        "target_required": "Seleziona almeno una lingua target",
        "queue_empty": "Nessun file in coda",
        "translation_done": "Traduzioni completate: {count}",
        "unexpected_error": "errore inatteso",
        "settings_locked": "Settings bloccate: usa variabili ambiente lato server (LOCK_TRANSLATOR_SETTINGS=1).",
        "endpoint_required": "Endpoint Azure obbligatorio",
        "endpoint_invalid": "Endpoint Azure non valido: deve iniziare con https://",
        "key_required": "Key Azure obbligatoria",
        "timeout_int": "Timeout non valido: usa un numero intero",
        "timeout_range": "Timeout non valido: usa un valore tra 30 e 3600 secondi",
        "batch_int": "Batch timeout/poll non validi: usa numeri interi",
        "batch_timeout_range": "Batch timeout non valido: usa un valore tra 60 e 7200 secondi",
        "batch_poll_range": "Batch poll non valido: usa un valore tra 2 e 60 secondi",
        "blob_incomplete": "Config Blob incompleta: inserisci connection string, source container e target container",
        "blob_url": "Blob connection string non valida: hai inserito un URL. Inserisci la connection string completa (DefaultEndpointsProtocol=...;AccountName=...;AccountKey=...;EndpointSuffix=...).",
        "blob_missing_parts": "Blob connection string non valida: devono essere presenti AccountName e AccountKey. Recuperala da Storage Account > Access keys > Connection string.",
        "settings_saved": "Impostazioni Azure Translator salvate",
    },
    "en": {
        "invalid_upload": "No valid file selected",
        "uploaded_files": "Uploaded {count} files",
        "onedrive_import_error": "OneDrive import error: {error}",
        "onedrive_imported": "Imported {count} files from OneDrive",
        "target_required": "Select at least one target language",
        "queue_empty": "No queued files",
        "translation_done": "Translations completed: {count}",
        "unexpected_error": "unexpected error",
        "settings_locked": "Settings are locked: use server-side environment variables (LOCK_TRANSLATOR_SETTINGS=1).",
        "endpoint_required": "Azure endpoint is required",
        "endpoint_invalid": "Invalid Azure endpoint: it must start with https://",
        "key_required": "Azure key is required",
        "timeout_int": "Invalid timeout: use an integer value",
        "timeout_range": "Invalid timeout: use a value between 30 and 3600 seconds",
        "batch_int": "Invalid batch timeout/poll: use integer values",
        "batch_timeout_range": "Invalid batch timeout: use a value between 60 and 7200 seconds",
        "batch_poll_range": "Invalid batch poll: use a value between 2 and 60 seconds",
        "blob_incomplete": "Incomplete Blob configuration: provide connection string, source container, and target container",
        "blob_url": "Invalid Blob connection string: a URL was provided. Use the full connection string (DefaultEndpointsProtocol=...;AccountName=...;AccountKey=...;EndpointSuffix=...).",
        "blob_missing_parts": "Invalid Blob connection string: AccountName and AccountKey are required. Retrieve it from Storage Account > Access keys > Connection string.",
        "settings_saved": "Azure Translator settings saved",
    },
}


def _list_incoming() -> list[Path]:
    return sorted([p for p in INCOMING_DIR.rglob("*") if p.is_file()], key=lambda p: p.name.lower())


def _list_processed(limit: int = 200) -> list[Path]:
    files = [
        p
        for p in PROCESSED_DIR.rglob("*")
        if (
            p.is_file()
            and p.name.startswith("translated_")
            and not any(part.startswith("_") for part in p.relative_to(PROCESSED_DIR).parts)
        )
    ]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:limit]


def _normalize_tab(tab: str | None) -> str:
    if (tab or "").strip().lower() == "settings":
        return "settings"
    return "workflow"


def _normalize_lang(lang: str | None) -> str:
    value = (lang or "").strip().lower()
    if value in UI_TEXTS:
        return value
    return "it"


def _rt(lang: str | None, key: str, **kwargs: object) -> str:
    lang_code = _normalize_lang(lang)
    template = RUNTIME_TEXTS.get(lang_code, RUNTIME_TEXTS["it"]).get(key, key)
    return template.format(**kwargs)


def _redirect_home(
    message: str | None = None,
    error: str | None = None,
    tab: str | None = None,
    lang: str | None = None,
) -> RedirectResponse:
    query_parts: list[str] = []
    normalized_tab = _normalize_tab(tab)
    normalized_lang = _normalize_lang(lang)
    if normalized_tab == "settings":
        query_parts.append("tab=settings")
    if normalized_lang != "it":
        query_parts.append(f"lang={normalized_lang}")
    if message:
        query_parts.append(f"message={quote_plus(message)}")
    if error:
        query_parts.append(f"error={quote_plus(error)}")
    query = "&".join(query_parts)
    url = "/" if not query else f"/?{query}"
    return RedirectResponse(url=url, status_code=303)


@app.get("/")
async def index(
    request: Request,
    message: str | None = None,
    error: str | None = None,
    tab: str | None = None,
    lang: str | None = None,
):
    saved_settings = load_translator_settings()
    effective_settings = get_effective_translator_config()
    active_tab = _normalize_tab(tab)
    lang_code = _normalize_lang(lang)
    onedrive_roots = [str(path).replace('\\', '/') for path in discover_local_onedrive_roots()]
    onedrive_folders = [str(path).replace('\\', '/') for path in discover_local_onedrive_folders()]

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "incoming": _list_incoming(),
            "processed": _list_processed(),
            "incoming_dir": INCOMING_DIR,
            "processed_dir": PROCESSED_DIR,
            "message": message,
            "error": error,
            "active_tab": active_tab,
            "lang_code": lang_code,
            "t": UI_TEXTS[lang_code],
            "onedrive_roots": onedrive_roots,
            "onedrive_folders": onedrive_folders,
            "settings_locked": is_translator_settings_locked(),
            "translator_settings": {
                "endpoint": saved_settings.get("endpoint", ""),
                "api_version": saved_settings.get("api_version", "2024-05-01"),
                "timeout_sec": saved_settings.get("timeout_sec", "600"),
                "has_key": bool(saved_settings.get("key", "").strip()),
                "masked_key": redact_key(saved_settings.get("key", "")),
                "blob_connection_string": saved_settings.get("blob_connection_string", ""),
                "masked_blob_connection_string": redact_connection_string(saved_settings.get("blob_connection_string", "")),
                "blob_source_container": saved_settings.get("blob_source_container", ""),
                "blob_target_container": saved_settings.get("blob_target_container", ""),
                "batch_api_version": saved_settings.get("batch_api_version", "2024-05-01"),
                "batch_timeout_sec": saved_settings.get("batch_timeout_sec", "1800"),
                "batch_poll_sec": saved_settings.get("batch_poll_sec", "5"),
                "is_blob_configured": bool(
                    effective_settings.get("blob_connection_string", "").strip()
                    and effective_settings.get("blob_source_container", "").strip()
                    and effective_settings.get("blob_target_container", "").strip()
                ),
                "effective_source": effective_settings.get("source", "settings"),
                "is_effective_configured": bool(
                    effective_settings.get("endpoint", "").strip() and effective_settings.get("key", "").strip()
                ),
            },
        },
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/upload-local")
async def upload_local(files: list[UploadFile] = File(...), lang: str = Form("it")):
    saved = 0
    for upload in files:
        if not upload.filename:
            continue
        safe_name = Path(upload.filename).name
        destination = DEFAULT_INCOMING_SUBDIR / safe_name
        content = await upload.read()
        destination.write_bytes(content)
        saved += 1

    if saved == 0:
        return _redirect_home(error=_rt(lang, "invalid_upload"), lang=lang)
    return _redirect_home(message=_rt(lang, "uploaded_files", count=saved), lang=lang)


@app.post("/import-onedrive")
async def import_onedrive(
    client_id: str = Form("local-sync"),
    tenant_id: str = Form("common"),
    folder_path: str = Form(...),
    recursive: str | None = Form(None),
    lang: str = Form("it"),
):
    try:
        imported = import_folder_from_onedrive(
            client_id=client_id,
            tenant_id=tenant_id,
            folder_path=folder_path,
            incoming_dir=DEFAULT_INCOMING_SUBDIR,
            recursive=recursive == "true",
            lang=lang,
        )
    except OneDriveImportError as exc:
        return _redirect_home(error=str(exc), lang=lang)
    except Exception as exc:  # noqa: BLE001
        return _redirect_home(error=_rt(lang, "onedrive_import_error", error=str(exc)), lang=lang)

    return _redirect_home(message=_rt(lang, "onedrive_imported", count=len(imported)), lang=lang)


@app.post("/process")
async def process_files(
    selected_files: list[str] | None = Form(None),
    source_lang: str = Form("pt"),
    target_langs: list[str] | None = Form(None),
    lang: str = Form("it"),
):
    source_lang = source_lang.strip().lower() or "pt"
    target_langs = target_langs or []
    if not target_langs:
        return _redirect_home(error=_rt(lang, "target_required"), tab="workflow", lang=lang)

    all_files = _list_incoming()
    if not all_files:
        return _redirect_home(error=_rt(lang, "queue_empty"), tab="workflow", lang=lang)

    selected_set = set(selected_files or [])
    files_to_process = [
        file_path for file_path in all_files if str(file_path.relative_to(INCOMING_DIR)).replace('\\', '/') in selected_set
    ]

    if not files_to_process:
        files_to_process = all_files

    run_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_root = PROCESSED_DIR / run_id

    completed = 0
    failures: list[str] = []

    for source_file in files_to_process:
        doc_dir = output_root / source_file.stem
        for target_lang in target_langs:
            try:
                translate_file_preserve_format(
                    source_path=source_file,
                    output_dir=doc_dir,
                    source_lang=source_lang,
                    target_lang=target_lang,
                )
                completed += 1
            except TranslationError as exc:
                rel = source_file.relative_to(INCOMING_DIR)
                failures.append(f"{rel} ({target_lang}): {exc}")
            except Exception as exc:  # noqa: BLE001
                rel = source_file.relative_to(INCOMING_DIR)
                failures.append(f"{rel} ({target_lang}): {_rt(lang, 'unexpected_error')}: {exc}")

    if failures:
        err = " | ".join(failures[:4])
        return _redirect_home(message=_rt(lang, "translation_done", count=completed), error=err, tab="workflow", lang=lang)

    return _redirect_home(message=_rt(lang, "translation_done", count=completed), tab="workflow", lang=lang)


@app.post("/settings/translator")
async def save_translator_settings_route(
    endpoint: str = Form(""),
    key: str = Form(""),
    api_version: str = Form("2024-05-01"),
    timeout_sec: str = Form("600"),
    blob_connection_string: str = Form(""),
    blob_source_container: str = Form(""),
    blob_target_container: str = Form(""),
    batch_api_version: str = Form("2024-05-01"),
    batch_timeout_sec: str = Form("1800"),
    batch_poll_sec: str = Form("5"),
    lang: str = Form("it"),
):
    if is_translator_settings_locked():
        return _redirect_home(
            error=_rt(lang, "settings_locked"),
            tab="settings",
            lang=lang,
        )

    current = load_translator_settings()

    endpoint = endpoint.strip()
    key = key.strip() or current.get("key", "").strip()
    api_version = api_version.strip() or "2024-05-01"
    timeout_sec = timeout_sec.strip() or "600"
    blob_connection_string = blob_connection_string.strip() or current.get("blob_connection_string", "").strip()
    blob_source_container = blob_source_container.strip() or current.get("blob_source_container", "").strip()
    blob_target_container = blob_target_container.strip() or current.get("blob_target_container", "").strip()
    batch_api_version = batch_api_version.strip() or "2024-05-01"
    batch_timeout_sec = batch_timeout_sec.strip() or "1800"
    batch_poll_sec = batch_poll_sec.strip() or "5"

    if not endpoint:
        return _redirect_home(error=_rt(lang, "endpoint_required"), tab="settings", lang=lang)
    if not endpoint.lower().startswith("https://"):
        return _redirect_home(error=_rt(lang, "endpoint_invalid"), tab="settings", lang=lang)
    if not key:
        return _redirect_home(error=_rt(lang, "key_required"), tab="settings", lang=lang)

    try:
        timeout_int = int(timeout_sec)
    except ValueError:
        return _redirect_home(error=_rt(lang, "timeout_int"), tab="settings", lang=lang)

    if timeout_int < 30 or timeout_int > 3600:
        return _redirect_home(error=_rt(lang, "timeout_range"), tab="settings", lang=lang)

    try:
        batch_timeout_int = int(batch_timeout_sec)
        batch_poll_int = int(batch_poll_sec)
    except ValueError:
        return _redirect_home(error=_rt(lang, "batch_int"), tab="settings", lang=lang)

    if batch_timeout_int < 60 or batch_timeout_int > 7200:
        return _redirect_home(error=_rt(lang, "batch_timeout_range"), tab="settings", lang=lang)
    if batch_poll_int < 2 or batch_poll_int > 60:
        return _redirect_home(error=_rt(lang, "batch_poll_range"), tab="settings", lang=lang)

    any_blob_value = bool(blob_connection_string or blob_source_container or blob_target_container)
    if any_blob_value and not (blob_connection_string and blob_source_container and blob_target_container):
        return _redirect_home(
            error=_rt(lang, "blob_incomplete"),
            tab="settings",
            lang=lang,
        )

    if blob_connection_string:
        blob_l = blob_connection_string.lower()
        if blob_l.startswith("http://") or blob_l.startswith("https://"):
            return _redirect_home(
                error=_rt(lang, "blob_url"),
                tab="settings",
                lang=lang,
            )
        if "accountkey=" not in blob_l or "accountname=" not in blob_l:
            return _redirect_home(
                error=_rt(lang, "blob_missing_parts"),
                tab="settings",
                lang=lang,
            )

    save_translator_settings(
        endpoint=endpoint,
        key=key,
        api_version=api_version,
        timeout_sec=str(timeout_int),
        blob_connection_string=blob_connection_string,
        blob_source_container=blob_source_container,
        blob_target_container=blob_target_container,
        batch_api_version=batch_api_version,
        batch_timeout_sec=str(batch_timeout_int),
        batch_poll_sec=str(batch_poll_int),
    )
    return _redirect_home(message=_rt(lang, "settings_saved"), tab="settings", lang=lang)
