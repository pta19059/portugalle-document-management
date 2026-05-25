from __future__ import annotations

from collections.abc import Iterable
import os
from pathlib import Path
import shutil
from urllib.parse import quote

import requests

try:
    import winreg
except ImportError:  # pragma: no cover
    winreg = None


SUPPORTED_IMPORT_EXTENSIONS = {
    ".pdf",
    ".txt",
    ".tsv",
    ".tab",
    ".csv",
    ".html",
    ".htm",
    ".mhtml",
    ".mht",
    ".pptx",
    ".xlsx",
    ".docx",
    ".msg",
    ".xlf",
}


class OneDriveImportError(RuntimeError):
    pass


RUNTIME_TEXTS = {
    "it": {
        "invalid_path": "Path OneDrive non valida: seleziona una cartella locale sincronizzata (es. C:/Users/<utente>/OneDrive/... ).",
        "no_supported_files": "Nessun file supportato trovato nella cartella selezionata. Formati importabili: pdf, docx, xlsx, pptx, txt, csv, html, msg, xlf.",
        "graph_missing_config": "Connettore OneDrive Graph non configurato. Imposta ONEDRIVE_TENANT_ID, ONEDRIVE_CLIENT_ID, ONEDRIVE_CLIENT_SECRET e ONEDRIVE_USER_ID.",
        "graph_auth_error": "Autenticazione OneDrive Graph fallita.",
        "graph_folder_not_found": "Cartella OneDrive non trovata o non accessibile.",
        "graph_api_error": "Errore OneDrive Graph: {error}",
    },
    "en": {
        "invalid_path": "Invalid OneDrive path: select a local synced folder (for example C:/Users/<user>/OneDrive/... ).",
        "no_supported_files": "No supported files were found in the selected folder. Supported formats: pdf, docx, xlsx, pptx, txt, csv, html, msg, xlf.",
        "graph_missing_config": "OneDrive Graph connector is not configured. Set ONEDRIVE_TENANT_ID, ONEDRIVE_CLIENT_ID, ONEDRIVE_CLIENT_SECRET, and ONEDRIVE_USER_ID.",
        "graph_auth_error": "OneDrive Graph authentication failed.",
        "graph_folder_not_found": "OneDrive folder not found or not accessible.",
        "graph_api_error": "OneDrive Graph error: {error}",
    },
}


def _normalize_lang(lang: str | None) -> str:
    if (lang or "").strip().lower() == "en":
        return "en"
    return "it"


def _rt(lang: str | None, key: str, **kwargs: object) -> str:
    template = RUNTIME_TEXTS[_normalize_lang(lang)].get(key, key)
    return template.format(**kwargs)


def get_onedrive_connector_mode() -> str:
    value = os.getenv("ONEDRIVE_CONNECTOR_MODE", "").strip().lower()
    if value in {"local-sync", "graph"}:
        return value

    required = (
        os.getenv("ONEDRIVE_TENANT_ID", "").strip(),
        os.getenv("ONEDRIVE_CLIENT_ID", "").strip(),
        os.getenv("ONEDRIVE_CLIENT_SECRET", "").strip(),
        os.getenv("ONEDRIVE_USER_ID", "").strip(),
    )
    if all(required):
        return "graph"
    return "local-sync"


def _graph_config() -> dict[str, str]:
    return {
        "tenant_id": os.getenv("ONEDRIVE_TENANT_ID", "").strip(),
        "client_id": os.getenv("ONEDRIVE_CLIENT_ID", "").strip(),
        "client_secret": os.getenv("ONEDRIVE_CLIENT_SECRET", "").strip(),
        "user_id": os.getenv("ONEDRIVE_USER_ID", "").strip(),
    }


def _require_graph_config(lang: str | None) -> dict[str, str]:
    config = _graph_config()
    if not all(config.values()):
        raise OneDriveImportError(_rt(lang, "graph_missing_config"))
    return config


def _graph_token(config: dict[str, str], lang: str | None) -> str:
    token_url = f"https://login.microsoftonline.com/{quote(config['tenant_id'], safe='')}/oauth2/v2.0/token"
    payload = {
        "grant_type": "client_credentials",
        "client_id": config["client_id"],
        "client_secret": config["client_secret"],
        "scope": "https://graph.microsoft.com/.default",
    }
    try:
        response = requests.post(token_url, data=payload, timeout=30)
    except Exception as exc:  # noqa: BLE001
        raise OneDriveImportError(_rt(lang, "graph_api_error", error=str(exc))) from exc

    if response.status_code >= 400:
        raise OneDriveImportError(_rt(lang, "graph_auth_error"))

    token = response.json().get("access_token", "")
    if not token:
        raise OneDriveImportError(_rt(lang, "graph_auth_error"))
    return token


def _graph_list_children(token: str, user_id: str, folder_path: str, lang: str | None) -> list[dict]:
    safe_user = quote(user_id, safe="")
    encoded_path = quote(folder_path, safe="/")
    if folder_path:
        url = f"https://graph.microsoft.com/v1.0/users/{safe_user}/drive/root:/{encoded_path}:/children"
    else:
        url = f"https://graph.microsoft.com/v1.0/users/{safe_user}/drive/root/children"

    items: list[dict] = []
    headers = {"Authorization": f"Bearer {token}"}
    while url:
        try:
            response = requests.get(url, headers=headers, timeout=30)
        except Exception as exc:  # noqa: BLE001
            raise OneDriveImportError(_rt(lang, "graph_api_error", error=str(exc))) from exc

        if response.status_code == 404:
            raise OneDriveImportError(_rt(lang, "graph_folder_not_found"))
        if response.status_code >= 400:
            raise OneDriveImportError(_rt(lang, "graph_api_error", error=f"HTTP {response.status_code}"))

        payload = response.json()
        items.extend(payload.get("value", []))
        url = payload.get("@odata.nextLink")

    return items


def _normalize_folder_path(folder_path: str) -> str:
    value = (folder_path or "").strip().replace("\\", "/")
    while "//" in value:
        value = value.replace("//", "/")
    return value.strip("/")


def _display_label_for_path(path: str) -> str:
    if len(path) <= 88:
        return path
    return "..." + path[-85:]


def _discover_graph_folders(max_results: int, max_depth: int, lang: str | None) -> list[str]:
    config = _require_graph_config(lang)
    token = _graph_token(config, lang)

    folders: list[str] = []
    queue: list[tuple[str, int]] = [("", 0)]
    seen: set[str] = set()

    while queue and len(folders) < max_results:
        current_path, depth = queue.pop(0)
        for item in _graph_list_children(token, config["user_id"], current_path, lang):
            if "folder" not in item:
                continue
            folder_name = str(item.get("name", "")).strip()
            if not folder_name:
                continue

            child_path = f"{current_path}/{folder_name}" if current_path else folder_name
            key = child_path.lower()
            if key in seen:
                continue
            seen.add(key)
            folders.append(child_path)
            if len(folders) >= max_results:
                break

            if depth + 1 < max_depth:
                queue.append((child_path, depth + 1))

    return sorted(folders, key=lambda p: p.lower())


def _add_if_valid(path: Path | None, collector: list[Path], seen: set[str]) -> None:
    if path is None:
        return

    try:
        resolved = path.expanduser().resolve(strict=False)
    except OSError:
        resolved = path.expanduser()

    key = str(resolved).lower()
    if key in seen:
        return

    seen.add(key)
    if resolved.exists() and resolved.is_dir():
        collector.append(resolved)


def _registry_onedrive_paths() -> Iterable[Path]:
    if winreg is None:
        return []

    results: list[Path] = []
    subkeys = [
        r"Software\Microsoft\OneDrive",
        r"Software\Microsoft\OneDrive\Accounts\Personal",
        r"Software\Microsoft\OneDrive\Accounts\Business1",
        r"Software\Microsoft\OneDrive\Accounts\Business2",
        r"Software\Microsoft\OneDrive\Accounts\Business3",
        r"Software\Microsoft\OneDrive\Accounts\Business4",
    ]

    for subkey in subkeys:
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey)
        except OSError:
            continue

        with key:
            for value_name in ("UserFolder", "MountPoint"):
                try:
                    value, _ = winreg.QueryValueEx(key, value_name)
                except OSError:
                    continue
                if isinstance(value, str) and value.strip():
                    results.append(Path(value.strip()))

    return results


def discover_local_onedrive_roots(max_results: int = 32) -> list[Path]:
    if get_onedrive_connector_mode() == "graph":
        try:
            config = _graph_config()
            if config.get("user_id"):
                return [Path(f"graph://{config['user_id']}")]
            return [Path("graph://configured")]
        except Exception:  # noqa: BLE001
            return []

    candidates: list[Path] = []
    seen: set[str] = set()

    for env_key in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        value = os.getenv(env_key, "").strip()
        if value:
            _add_if_valid(Path(value), candidates, seen)

    for reg_path in _registry_onedrive_paths():
        _add_if_valid(reg_path, candidates, seen)

    user_profile = os.getenv("USERPROFILE", "").strip()
    if user_profile:
        profile = Path(user_profile)
        _add_if_valid(profile / "OneDrive", candidates, seen)
        for folder in profile.glob("OneDrive*"):
            _add_if_valid(folder, candidates, seen)

    home = Path.home()
    _add_if_valid(home / "OneDrive", candidates, seen)
    for folder in home.glob("OneDrive*"):
        _add_if_valid(folder, candidates, seen)

    users_dir = Path("C:/Users")
    if users_dir.exists() and users_dir.is_dir():
        for profile_dir in users_dir.iterdir():
            if not profile_dir.is_dir():
                continue
            _add_if_valid(profile_dir / "OneDrive", candidates, seen)
            for folder in profile_dir.glob("OneDrive*"):
                _add_if_valid(folder, candidates, seen)

    if len(candidates) > max_results:
        return sorted(candidates, key=lambda p: p.name.lower())[:max_results]
    return sorted(candidates, key=lambda p: p.name.lower())


def discover_local_onedrive_folders(max_results: int = 120, max_depth: int = 2) -> list[Path]:
    if get_onedrive_connector_mode() == "graph":
        try:
            graph_folders = _discover_graph_folders(max_results=max_results, max_depth=max_depth, lang="en")
            return [Path(folder) for folder in graph_folders]
        except Exception:  # noqa: BLE001
            return []

    folders: list[Path] = []
    seen: set[str] = set()

    roots = discover_local_onedrive_roots(max_results=32)
    for root in roots:
        _add_if_valid(root, folders, seen)

        try:
            for child in root.rglob("*"):
                if not child.is_dir():
                    continue
                depth = len(child.relative_to(root).parts)
                if depth > max_depth:
                    continue
                _add_if_valid(child, folders, seen)
                if len(folders) >= max_results:
                    return sorted(folders, key=lambda p: str(p).lower())
        except OSError:
            continue

    return sorted(folders, key=lambda p: str(p).lower())


def import_folder_from_onedrive(
    client_id: str,
    tenant_id: str,
    folder_path: str,
    incoming_dir: Path,
    recursive: bool,
    lang: str = "it",
) -> list[Path]:
    _ = (client_id, tenant_id)

    if get_onedrive_connector_mode() == "graph":
        config = _require_graph_config(lang)
        token = _graph_token(config, lang)
        selected_path = _normalize_folder_path(folder_path)

        incoming_dir.mkdir(parents=True, exist_ok=True)

        queue: list[tuple[str, str]] = [(selected_path, "")]
        files_to_download: list[tuple[str, str]] = []

        while queue:
            api_path, relative_prefix = queue.pop(0)
            children = _graph_list_children(token, config["user_id"], api_path, lang)

            for item in children:
                name = str(item.get("name", "")).strip()
                if not name:
                    continue

                relative_path = f"{relative_prefix}/{name}" if relative_prefix else name
                if "folder" in item:
                    if recursive:
                        child_api_path = f"{api_path}/{name}" if api_path else name
                        queue.append((child_api_path, relative_path))
                    continue

                if Path(name).suffix.lower() not in SUPPORTED_IMPORT_EXTENSIONS:
                    continue

                item_id = str(item.get("id", "")).strip()
                if not item_id:
                    continue
                files_to_download.append((item_id, relative_path))

        if not files_to_download:
            raise OneDriveImportError(_rt(lang, "no_supported_files"))

        imported: list[Path] = []
        safe_user = quote(config["user_id"], safe="")
        headers = {"Authorization": f"Bearer {token}"}
        for item_id, relative_path in files_to_download:
            safe_item_id = quote(item_id, safe="")
            content_url = f"https://graph.microsoft.com/v1.0/users/{safe_user}/drive/items/{safe_item_id}/content"
            try:
                response = requests.get(content_url, headers=headers, timeout=120)
            except Exception as exc:  # noqa: BLE001
                raise OneDriveImportError(_rt(lang, "graph_api_error", error=str(exc))) from exc

            if response.status_code >= 400:
                raise OneDriveImportError(_rt(lang, "graph_api_error", error=f"HTTP {response.status_code}"))

            relative = Path(relative_path)
            destination = incoming_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(response.content)
            imported.append(destination)

        return imported

    source_folder = Path(folder_path).expanduser()
    if not source_folder.exists() or not source_folder.is_dir():
        raise OneDriveImportError(_rt(lang, "invalid_path"))

    incoming_dir.mkdir(parents=True, exist_ok=True)

    iterator = source_folder.rglob("*") if recursive else source_folder.glob("*")
    source_files = [p for p in iterator if p.is_file() and p.suffix.lower() in SUPPORTED_IMPORT_EXTENSIONS]

    if not source_files:
        raise OneDriveImportError(_rt(lang, "no_supported_files"))

    imported: list[Path] = []
    for src in source_files:
        relative = src.relative_to(source_folder)
        destination = incoming_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, destination)
        imported.append(destination)

    return imported
