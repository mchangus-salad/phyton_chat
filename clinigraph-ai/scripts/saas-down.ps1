param(
    [string]$EnvFile = ".env.saas.local",
    [switch]$KeepVolumes,
    [switch]$KeepImage,
    [switch]$KeepEnvFile
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Yellow
}

function Invoke-Compose {
    param([string[]]$ComposeArgs)

    & docker compose @ComposeArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Fallo docker compose: $($ComposeArgs -join ' ')"
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
Set-Location $repoRoot

$composeFile = Join-Path $repoRoot "docker-compose.saas.yml"
$envLocalFile = Join-Path $repoRoot $EnvFile
$envExampleFile = Join-Path $repoRoot ".env.saas.example"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker no esta disponible en PATH."
}

$resolvedEnvFile = $envLocalFile
if (-not (Test-Path $resolvedEnvFile) -and (Test-Path $envExampleFile)) {
    $resolvedEnvFile = $envExampleFile
}

$composeArgs = @("-f", $composeFile, "--env-file", $resolvedEnvFile, "down")
if (-not $KeepVolumes) {
    $composeArgs += "--volumes"
}
if (-not $KeepImage) {
    $composeArgs += "--rmi"
    $composeArgs += "local"
}
$composeArgs += "--remove-orphans"

Write-Step "Apagando y limpiando stack SaaS"
Invoke-Compose -ComposeArgs $composeArgs

if ((-not $KeepEnvFile) -and (Test-Path $envLocalFile)) {
    Write-Step "Eliminando entorno local SaaS"
    Remove-Item $envLocalFile -Force
}

Write-Step "Limpieza completada"
Write-Host "Si necesitas reinstalar: .\scripts\saas-up.ps1"