from __future__ import annotations

from collections.abc import Iterable
import os
from pathlib import Path
import shutil

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
    },
    "en": {
        "invalid_path": "Invalid OneDrive path: select a local synced folder (for example C:/Users/<user>/OneDrive/... ).",
        "no_supported_files": "No supported files were found in the selected folder. Supported formats: pdf, docx, xlsx, pptx, txt, csv, html, msg, xlf.",
    },
}


def _normalize_lang(lang: str | None) -> str:
    if (lang or "").strip().lower() == "en":
        return "en"
    return "it"


def _rt(lang: str | None, key: str) -> str:
    return RUNTIME_TEXTS[_normalize_lang(lang)].get(key, key)


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
