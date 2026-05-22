from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from azure.storage.blob import (
    BlobSasPermissions,
    BlobServiceClient,
    ContainerSasPermissions,
    generate_blob_sas,
    generate_container_sas,
)
from azure.core.exceptions import ResourceExistsError

from .settings_store import get_effective_translator_config
from .translator import TranslationError


def _required(value: str, field_name: str) -> str:
    value = value.strip()
    if not value:
        raise TranslationError(f"Configurazione Azure mancante: {field_name}")
    return value


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


def _connection_string_value(connection_string: str, key: str) -> str:
    prefix = f"{key}="
    for part in connection_string.split(";"):
        token = part.strip()
        if token.startswith(prefix):
            return token[len(prefix) :]
    return ""


def _build_batch_url(endpoint: str, api_version: str) -> str:
    endpoint = endpoint.rstrip("/")
    return f"{endpoint}/translator/document/batches?api-version={api_version}"


def _parse_operation_id(operation_location: str) -> str:
    # Example: .../translator/document/<id>?api-version=2024-05-01
    marker = "/translator/document/"
    idx = operation_location.find(marker)
    if idx < 0:
        return ""
    tail = operation_location[idx + len(marker) :]
    return tail.split("?", 1)[0].strip()


def _safe_delete_blob(container_client, blob_name: str) -> None:
    try:
        container_client.delete_blob(blob_name)
    except Exception:
        pass


def translate_pdf_with_azure_batch_blob(
    source_path: Path,
    target_path: Path,
    source_lang: str,
    target_lang: str,
) -> None:
    config = get_effective_translator_config()

    endpoint = _required(config.get("endpoint", ""), "endpoint")
    key = _required(config.get("key", ""), "key")
    batch_api_version = config.get("batch_api_version", "2024-05-01").strip() or "2024-05-01"

    connection_string = _required(config.get("blob_connection_string", ""), "blob_connection_string")
    source_container_name = _required(config.get("blob_source_container", ""), "blob_source_container")
    target_container_name = _required(config.get("blob_target_container", ""), "blob_target_container")

    if not source_path.exists():
        raise TranslationError(f"File sorgente non trovato: {source_path}")

    try:
        batch_timeout_sec = int(config.get("batch_timeout_sec", "1800").strip() or "1800")
        batch_poll_sec = int(config.get("batch_poll_sec", "5").strip() or "5")
    except ValueError as exc:
        raise TranslationError("Configurazione batch non valida: timeout/poll devono essere numeri interi") from exc

    batch_timeout_sec = max(60, batch_timeout_sec)
    batch_poll_sec = max(2, batch_poll_sec)

    account_key = _connection_string_value(connection_string, "AccountKey")
    if not account_key:
        raise TranslationError("Blob connection string non valida: AccountKey mancante")

    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
    account_name = blob_service_client.account_name

    source_container_client = blob_service_client.get_container_client(source_container_name)
    target_container_client = blob_service_client.get_container_client(target_container_name)

    try:
        source_container_client.create_container()
    except ResourceExistsError:
        pass

    try:
        target_container_client.create_container()
    except ResourceExistsError:
        pass

    job_id = uuid.uuid4().hex
    source_blob_name = f"jobs/{job_id}/source/{source_path.name}"
    target_blob_name = f"jobs/{job_id}/target/{target_path.name}"

    source_blob_client = source_container_client.get_blob_client(source_blob_name)
    with source_path.open("rb") as fh:
        source_blob_client.upload_blob(fh, overwrite=True)

    expiry = datetime.now(timezone.utc) + timedelta(hours=2)
    source_blob_sas = generate_blob_sas(
        account_name=account_name,
        account_key=account_key,
        container_name=source_container_name,
        blob_name=source_blob_name,
        permission=BlobSasPermissions(read=True),
        expiry=expiry,
    )
    target_container_sas = generate_container_sas(
        account_name=account_name,
        account_key=account_key,
        container_name=target_container_name,
        permission=ContainerSasPermissions(read=True, write=True, list=True),
        expiry=expiry,
    )

    source_url = f"{source_blob_client.url}?{source_blob_sas}"
    target_blob_url = f"{target_container_client.url}/{target_blob_name}?{target_container_sas}"

    body = {
        "inputs": [
            {
                "storageType": "File",
                "source": {
                    "sourceUrl": source_url,
                    "language": source_lang,
                    "storageSource": "AzureBlob",
                },
                "targets": [
                    {
                        "targetUrl": target_blob_url,
                        "language": target_lang,
                        "storageSource": "AzureBlob",
                    }
                ],
            }
        ]
    }

    headers = {
        "Ocp-Apim-Subscription-Key": key,
        "Content-Type": "application/json",
    }

    batch_url = _build_batch_url(endpoint, batch_api_version)
    start_response = requests.post(batch_url, headers=headers, json=body, timeout=60)
    if start_response.status_code != 202:
        detail = _extract_error_message(start_response)
        raise TranslationError(f"Azure Batch start error ({start_response.status_code}): {detail}")

    operation_location = start_response.headers.get("Operation-Location", "").strip()
    if not operation_location:
        raise TranslationError("Risposta Azure Batch non valida: header Operation-Location mancante")

    deadline = time.time() + batch_timeout_sec
    status = "NotStarted"
    terminal_statuses = {"Succeeded", "Failed", "ValidationFailed", "Cancelled", "Cancelling"}

    while time.time() < deadline:
        poll_response = requests.get(operation_location, headers={"Ocp-Apim-Subscription-Key": key}, timeout=30)
        if poll_response.status_code != 200:
            detail = _extract_error_message(poll_response)
            raise TranslationError(f"Azure Batch poll error ({poll_response.status_code}): {detail}")

        data = poll_response.json()
        raw_status = data.get("status", "")
        status = raw_status if isinstance(raw_status, str) else ""

        if status in terminal_statuses:
            if status == "Succeeded":
                break

            operation_id = _parse_operation_id(operation_location)
            msg = f"Job batch terminato con stato: {status}"
            if operation_id:
                msg += f" (jobId={operation_id})"
            raise TranslationError(msg)

        time.sleep(batch_poll_sec)

    if status != "Succeeded":
        raise TranslationError("Timeout attesa Azure Batch: job non completato nei tempi previsti")

    target_blob_client = target_container_client.get_blob_client(target_blob_name)
    if not target_blob_client.exists():
        raise TranslationError("Output PDF non trovato nel target container Blob")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    data = target_blob_client.download_blob().readall()
    target_path.write_bytes(data)

    _safe_delete_blob(source_container_client, source_blob_name)
    _safe_delete_blob(target_container_client, target_blob_name)
