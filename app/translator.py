from __future__ import annotations

import os
from typing import Any

import requests


class TranslationError(RuntimeError):
    pass


def _translate_with_libretranslate(text: str, source_lang: str, target_lang: str) -> str:
    base_url = os.getenv("LIBRETRANSLATE_URL", "http://127.0.0.1:5000").rstrip("/")
    api_key = os.getenv("LIBRETRANSLATE_API_KEY", "")

    payload: dict[str, Any] = {
        "q": text,
        "source": source_lang,
        "target": target_lang,
        "format": "text",
    }
    if api_key:
        payload["api_key"] = api_key

    response = requests.post(f"{base_url}/translate", json=payload, timeout=120)
    response.raise_for_status()

    data = response.json()
    translated = data.get("translatedText")
    if not isinstance(translated, str):
        raise TranslationError("Risposta non valida da LibreTranslate")
    return translated


def translate_text(text: str, source_lang: str, target_lang: str) -> str:
    backend = os.getenv("TRANSLATION_BACKEND", "libretranslate").lower().strip()

    if not text.strip():
        return text

    if backend != "libretranslate":
        raise TranslationError(f"Backend non supportato: {backend}")

    try:
        return _translate_with_libretranslate(text, source_lang, target_lang)
    except Exception as exc:  # noqa: BLE001
        raise TranslationError(f"LibreTranslate translation error: {exc}") from exc
