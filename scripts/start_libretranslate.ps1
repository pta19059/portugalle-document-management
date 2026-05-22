Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

param(
  [switch]$UpdateModels
)

Set-Location (Join-Path $PSScriptRoot "..")

$containerName = "libretranslate-local"

$dockerReady = $false
try {
  docker info | Out-Null
  $dockerReady = $true
} catch {
  $dockerReady = $false
}

if ($dockerReady) {
  try {
    docker rm -f $containerName | Out-Null
  } catch {
  }

  if ($UpdateModels) {
    docker pull libretranslate/libretranslate:latest
  }

  docker run -d --name $containerName -p 5000:5000 libretranslate/libretranslate:latest | Out-Null
  Write-Host "LibreTranslate avviato in Docker su http://127.0.0.1:5000"
  exit 0
}

if (-not (Test-Path ".venv-libretranslate")) {
  python -m venv .venv-libretranslate
}

$python = Join-Path (Get-Location) ".venv-libretranslate\Scripts\python.exe"
& $python -m pip install --upgrade pip
& $python -m pip install libretranslate

Start-Process -FilePath $python -ArgumentList "-m", "libretranslate", "--host", "127.0.0.1", "--port", "5000"
Write-Host "LibreTranslate avviato localmente su http://127.0.0.1:5000"
