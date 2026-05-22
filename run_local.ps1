Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

if (-not (Test-Path ".venv-app")) {
  python -m venv .venv-app
}

$python = Join-Path $PSScriptRoot ".venv-app\Scripts\python.exe"

& $python -m pip install --upgrade pip
& $python -m pip install -r requirements.txt

$env:TRANSLATION_BACKEND = "azure_document"
if (-not $env:AZURE_TRANSLATOR_API_VERSION) {
  $env:AZURE_TRANSLATOR_API_VERSION = "2024-05-01"
}

if (-not $env:AZURE_TRANSLATOR_ENDPOINT) {
  throw "Imposta AZURE_TRANSLATOR_ENDPOINT (es: https://<resource-name>.cognitiveservices.azure.com)"
}

if (-not $env:AZURE_TRANSLATOR_KEY) {
  throw "Imposta AZURE_TRANSLATOR_KEY con la key della risorsa Azure Translator"
}

& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
