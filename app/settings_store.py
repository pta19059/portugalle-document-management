from __future__ import annotations

import json
import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
SETTINGS_DIR = BASE_DIR / "data" / "settings"
TRANSLATOR_SETTINGS_FILE = SETTINGS_DIR / "translator_settings.json"


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def is_translator_settings_locked() -> bool:
    return _truthy(os.getenv("LOCK_TRANSLATOR_SETTINGS"))


def load_translator_settings() -> dict[str, str]:
    if not TRANSLATOR_SETTINGS_FILE.exists():
        return {
            "endpoint": "",
            "key": "",
            "api_version": "2024-05-01",
            "timeout_sec": "600",
            "blob_connection_string": "",
            "blob_source_container": "",
            "blob_target_container": "",
            "batch_api_version": "2024-05-01",
            "batch_timeout_sec": "1800",
            "batch_poll_sec": "5",
        }

    try:
        data = json.loads(TRANSLATOR_SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = {}

    return {
        "endpoint": str(data.get("endpoint", "")).strip(),
        "key": str(data.get("key", "")).strip(),
        "api_version": str(data.get("api_version", "2024-05-01")).strip() or "2024-05-01",
        "timeout_sec": str(data.get("timeout_sec", "600")).strip() or "600",
        "blob_connection_string": str(data.get("blob_connection_string", "")).strip(),
        "blob_source_container": str(data.get("blob_source_container", "")).strip(),
        "blob_target_container": str(data.get("blob_target_container", "")).strip(),
        "batch_api_version": str(data.get("batch_api_version", "2024-05-01")).strip() or "2024-05-01",
        "batch_timeout_sec": str(data.get("batch_timeout_sec", "1800")).strip() or "1800",
        "batch_poll_sec": str(data.get("batch_poll_sec", "5")).strip() or "5",
    }


def save_translator_settings(
    endpoint: str,
    key: str,
    api_version: str,
    timeout_sec: str,
    blob_connection_string: str,
    blob_source_container: str,
    blob_target_container: str,
    batch_api_version: str,
    batch_timeout_sec: str,
    batch_poll_sec: str,
) -> None:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "endpoint": endpoint.strip(),
        "key": key.strip(),
        "api_version": (api_version.strip() or "2024-05-01"),
        "timeout_sec": (timeout_sec.strip() or "600"),
        "blob_connection_string": blob_connection_string.strip(),
        "blob_source_container": blob_source_container.strip(),
        "blob_target_container": blob_target_container.strip(),
        "batch_api_version": (batch_api_version.strip() or "2024-05-01"),
        "batch_timeout_sec": (batch_timeout_sec.strip() or "1800"),
        "batch_poll_sec": (batch_poll_sec.strip() or "5"),
    }
    TRANSLATOR_SETTINGS_FILE.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def get_effective_translator_config() -> dict[str, str]:
    saved = load_translator_settings()

    # Environment variables take precedence for production/public deployments.
    endpoint = os.getenv("AZURE_TRANSLATOR_ENDPOINT", "").strip() or saved["endpoint"]
    key = os.getenv("AZURE_TRANSLATOR_KEY", "").strip() or saved["key"]
    api_version = os.getenv("AZURE_TRANSLATOR_API_VERSION", "").strip() or saved["api_version"]
    timeout_sec = os.getenv("AZURE_TRANSLATOR_TIMEOUT_SEC", "").strip() or saved["timeout_sec"]
    blob_connection_string = os.getenv("AZURE_BLOB_CONNECTION_STRING", "").strip() or saved["blob_connection_string"]
    blob_source_container = os.getenv("AZURE_BLOB_SOURCE_CONTAINER", "").strip() or saved["blob_source_container"]
    blob_target_container = os.getenv("AZURE_BLOB_TARGET_CONTAINER", "").strip() or saved["blob_target_container"]
    batch_api_version = os.getenv("AZURE_TRANSLATOR_BATCH_API_VERSION", "").strip() or saved["batch_api_version"]
    batch_timeout_sec = os.getenv("AZURE_TRANSLATOR_BATCH_TIMEOUT_SEC", "").strip() or saved["batch_timeout_sec"]
    batch_poll_sec = os.getenv("AZURE_TRANSLATOR_BATCH_POLL_SEC", "").strip() or saved["batch_poll_sec"]

    source = "environment" if (
        os.getenv("AZURE_TRANSLATOR_ENDPOINT")
        or os.getenv("AZURE_TRANSLATOR_KEY")
        or os.getenv("AZURE_BLOB_CONNECTION_STRING")
    ) else "settings"

    return {
        "endpoint": endpoint,
        "key": key,
        "api_version": api_version or "2024-05-01",
        "timeout_sec": timeout_sec or "600",
        "blob_connection_string": blob_connection_string,
        "blob_source_container": blob_source_container,
        "blob_target_container": blob_target_container,
        "batch_api_version": batch_api_version or "2024-05-01",
        "batch_timeout_sec": batch_timeout_sec or "1800",
        "batch_poll_sec": batch_poll_sec or "5",
        "source": source,
    }


def redact_key(key: str) -> str:
    key = key.strip()
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}{'*' * (len(key) - 8)}{key[-4:]}"


def redact_connection_string(value: str) -> str:
    value = value.strip()
    if not value:
        return ""

    parts = value.split(";")
    redacted_parts: list[str] = []
    for part in parts:
        if "=" not in part:
            redacted_parts.append(part)
            continue
        key, raw_val = part.split("=", 1)
        k = key.strip().lower()
        if k in {"accountkey", "sharedaccesssignature"} and raw_val:
            redacted_parts.append(f"{key}=***")
        else:
            redacted_parts.append(part)
    return ";".join(redacted_parts)
