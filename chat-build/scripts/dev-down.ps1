param(
    [switch]$RemoveVolumes,
    [switch]$RemoveOrphans
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Yellow
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
Set-Location $repoRoot

$composeFile = Join-Path $repoRoot "docker-compose.local.yml"

$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) {
    throw "Docker no esta disponible."
}

$args = @("compose", "-f", $composeFile, "down")
if ($RemoveVolumes) {
    $args += "-v"
}
if ($RemoveOrphans) {
    $args += "--remove-orphans"
}

Write-Step "Apagando stack local"
& docker @args
if ($LASTEXITCODE -ne 0) {
    throw "Fallo al apagar docker compose."
}

Write-Step "Stack local detenido"
Write-Host "Si necesitas arrancar de nuevo: .\\scripts\\dev-up.ps1"