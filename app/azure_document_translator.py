from __future__ import annotations

import json
import mimetypes
import os
from pathlib import Path

import requests

from .settings_store import get_effective_translator_config
from .translator import TranslationError


def _required(value: str, field_name: str) -> str:
    value = value.strip()
    if not value:
        raise TranslationError(f"Configurazione Azure mancante: {field_name}")
    return value


def _build_url(endpoint: str, api_version: str, source_lang: str, target_lang: str) -> str:
    endpoint = endpoint.rstrip("/")
    return (
        f"{endpoint}/translator/document:translate"
        f"?api-version={api_version}&sourceLanguage={source_lang}&targetLanguage={target_lang}"
    )


def _extract_error_message(response: requests.Response) -> str:
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return response.text.strip() or f"HTTP {response.status_code}"

    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict):
            msg = err.get("message")
            if isinstance(msg, str) and msg.strip():
                return msg.strip()
        msg = payload.get("message")
        if isinstance(msg, str) and msg.strip():
            return msg.strip()

    return json.dumps(payload, ensure_ascii=True)


def translate_document_with_azure(
    source_path: Path,
    target_path: Path,
    source_lang: str,
    target_lang: str,
) -> None:
    config = get_effective_translator_config()
    endpoint = _required(config.get("endpoint", ""), "endpoint")
    key = _required(config.get("key", ""), "key")
    api_version = config.get("api_version", "2024-05-01").strip() or "2024-05-01"
    timeout_raw = config.get("timeout_sec", "600").strip() or "600"

    try:
        timeout_sec = int(timeout_raw)
    except ValueError as exc:
        raise TranslationError("Configurazione Azure non valida: timeout_sec deve essere un numero intero") from exc

    if timeout_sec < 30:
        timeout_sec = 30

    if not source_path.exists():
        raise TranslationError(f"File sorgente non trovato: {source_path}")

    url = _build_url(endpoint, api_version, source_lang, target_lang)
    content_type = mimetypes.guess_type(str(source_path))[0] or "application/octet-stream"

    headers = {
        "Ocp-Apim-Subscription-Key": key,
    }

    with source_path.open("rb") as f:
        files = {
            "document": (source_path.name, f, content_type),
        }
        response = requests.post(url, headers=headers, files=files, timeout=timeout_sec)

    if response.status_code != 200:
        detail = _extract_error_message(response)
        raise TranslationError(f"Azure Document Translator error ({response.status_code}): {detail}")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(response.content)
