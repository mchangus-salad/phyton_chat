$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Green
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
Set-Location $repoRoot

$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "No existe .venv. Ejecuta primero .\\scripts\\dev-up.ps1 -NoServer"
}

Write-Step "Sembrando datos iniciales en Weaviate"
& $venvPython manage.py seed_weaviate
if ($LASTEXITCODE -ne 0) {
    throw "Fallo al ejecutar seed_weaviate"
}

Write-Step "Sembrando usuarios locales por rol"
& $venvPython manage.py seed_local_users
if ($LASTEXITCODE -ne 0) {
    throw "Fallo al ejecutar seed_local_users"
}

Write-Step "Seed completado"
