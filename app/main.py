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


def _redirect_home(message: str | None = None, error: str | None = None, tab: str | None = None) -> RedirectResponse:
    query_parts: list[str] = []
    normalized_tab = _normalize_tab(tab)
    if normalized_tab == "settings":
        query_parts.append("tab=settings")
    if message:
        query_parts.append(f"message={quote_plus(message)}")
    if error:
        query_parts.append(f"error={quote_plus(error)}")
    query = "&".join(query_parts)
    url = "/" if not query else f"/?{query}"
    return RedirectResponse(url=url, status_code=303)


@app.get("/")
async def index(request: Request, message: str | None = None, error: str | None = None, tab: str | None = None):
    saved_settings = load_translator_settings()
    effective_settings = get_effective_translator_config()
    active_tab = _normalize_tab(tab)
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
async def upload_local(files: list[UploadFile] = File(...)):
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
        return _redirect_home(error="Nessun file valido selezionato")
    return _redirect_home(message=f"Caricati {saved} file")


@app.post("/import-onedrive")
async def import_onedrive(
    client_id: str = Form("local-sync"),
    tenant_id: str = Form("common"),
    folder_path: str = Form(...),
    recursive: str | None = Form(None),
):
    try:
        imported = import_folder_from_onedrive(
            client_id=client_id,
            tenant_id=tenant_id,
            folder_path=folder_path,
            incoming_dir=DEFAULT_INCOMING_SUBDIR,
            recursive=recursive == "true",
        )
    except OneDriveImportError as exc:
        return _redirect_home(error=str(exc))
    except Exception as exc:  # noqa: BLE001
        return _redirect_home(error=f"Errore import OneDrive: {exc}")

    return _redirect_home(message=f"Importati {len(imported)} file da OneDrive")


@app.post("/process")
async def process_files(
    selected_files: list[str] | None = Form(None),
    source_lang: str = Form("pt"),
    target_langs: list[str] | None = Form(None),
):
    source_lang = source_lang.strip().lower() or "pt"
    target_langs = target_langs or []
    if not target_langs:
        return _redirect_home(error="Seleziona almeno una lingua target", tab="workflow")

    all_files = _list_incoming()
    if not all_files:
        return _redirect_home(error="Nessun file in coda", tab="workflow")

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
                failures.append(f"{rel} ({target_lang}): errore inatteso: {exc}")

    if failures:
        err = " | ".join(failures[:4])
        return _redirect_home(message=f"Traduzioni completate: {completed}", error=err, tab="workflow")

    return _redirect_home(message=f"Traduzioni completate: {completed}", tab="workflow")


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
):
    if is_translator_settings_locked():
        return _redirect_home(
            error="Settings bloccate: usa variabili ambiente lato server (LOCK_TRANSLATOR_SETTINGS=1).",
            tab="settings",
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
        return _redirect_home(error="Endpoint Azure obbligatorio", tab="settings")
    if not endpoint.lower().startswith("https://"):
        return _redirect_home(error="Endpoint Azure non valido: deve iniziare con https://", tab="settings")
    if not key:
        return _redirect_home(error="Key Azure obbligatoria", tab="settings")

    try:
        timeout_int = int(timeout_sec)
    except ValueError:
        return _redirect_home(error="Timeout non valido: usa un numero intero", tab="settings")

    if timeout_int < 30 or timeout_int > 3600:
        return _redirect_home(error="Timeout non valido: usa un valore tra 30 e 3600 secondi", tab="settings")

    try:
        batch_timeout_int = int(batch_timeout_sec)
        batch_poll_int = int(batch_poll_sec)
    except ValueError:
        return _redirect_home(error="Batch timeout/poll non validi: usa numeri interi", tab="settings")

    if batch_timeout_int < 60 or batch_timeout_int > 7200:
        return _redirect_home(error="Batch timeout non valido: usa un valore tra 60 e 7200 secondi", tab="settings")
    if batch_poll_int < 2 or batch_poll_int > 60:
        return _redirect_home(error="Batch poll non valido: usa un valore tra 2 e 60 secondi", tab="settings")

    any_blob_value = bool(blob_connection_string or blob_source_container or blob_target_container)
    if any_blob_value and not (blob_connection_string and blob_source_container and blob_target_container):
        return _redirect_home(
            error="Config Blob incompleta: inserisci connection string, source container e target container",
            tab="settings",
        )

    if blob_connection_string:
        blob_l = blob_connection_string.lower()
        if blob_l.startswith("http://") or blob_l.startswith("https://"):
            return _redirect_home(
                error=(
                    "Blob connection string non valida: hai inserito un URL. "
                    "Inserisci la connection string completa (DefaultEndpointsProtocol=...;AccountName=...;AccountKey=...;EndpointSuffix=...)."
                ),
                tab="settings",
            )
        if "accountkey=" not in blob_l or "accountname=" not in blob_l:
            return _redirect_home(
                error=(
                    "Blob connection string non valida: devono essere presenti AccountName e AccountKey. "
                    "Recuperala da Storage Account > Access keys > Connection string."
                ),
                tab="settings",
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
    return _redirect_home(message="Impostazioni Azure Translator salvate", tab="settings")
