from __future__ import annotations

from pathlib import Path

from .azure_document_translator import translate_document_with_azure
from .azure_pdf_batch_translator import translate_pdf_with_azure_batch_blob
from .translator import TranslationError


SYNC_SUPPORTED_EXTENSIONS = {
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


def translate_file_preserve_format(
    source_path: Path,
    output_dir: Path,
    source_lang: str,
    target_lang: str,
) -> Path:
    ext = source_path.suffix.lower()

    if ext == ".pdf":
        output_dir.mkdir(parents=True, exist_ok=True)
        target_path = output_dir / f"translated_{target_lang}{ext}"
        translate_pdf_with_azure_batch_blob(source_path, target_path, source_lang, target_lang)
        return target_path

    if ext not in SYNC_SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SYNC_SUPPORTED_EXTENSIONS))
        raise TranslationError(
            f"Formato non supportato da Azure Document Translator (sync): {ext or '<senza estensione>'}. "
            f"Formati supportati: {supported}. "
            "Per PDF e abilitata la modalita batch con Blob Storage; configura Blob nella tab Settings."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / f"translated_{target_lang}{ext}"

    try:
        translate_document_with_azure(source_path, target_path, source_lang, target_lang)
        return target_path
    except TranslationError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise TranslationError(f"Azure Document Translator error: {exc}") from exc
