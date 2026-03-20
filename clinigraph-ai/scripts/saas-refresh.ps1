param(
    [string]$EnvFile = ".env.saas.local",
    [switch]$Pull,
    [switch]$NoBuild,
    [switch]$RestartOnly,
    [int]$TimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Green
}

function Get-EnvSetting {
    param(
        [string]$FilePath,
        [string]$Key,
        [string]$DefaultValue = ""
    )

    if (-not (Test-Path $FilePath)) {
        return $DefaultValue
    }

    $line = Get-Content $FilePath | Where-Object { $_ -match "^$Key=" } | Select-Object -First 1
    if (-not $line) {
        return $DefaultValue
    }

    $value = $line.Substring($Key.Length + 1).Trim()
    if ([string]::IsNullOrWhiteSpace($value)) {
        return $DefaultValue
    }

    return $value
}

function Invoke-Compose {
    param([string[]]$ComposeArgs)

    & docker compose @ComposeArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Fallo docker compose: $($ComposeArgs -join ' ')"
    }
}

function Wait-ForHealthEndpoint {
    param(
        [string]$Url,
        [int]$TimeoutSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-RestMethod -Method Get -Uri $Url
            if ($response -and $response.status -eq "ok") {
                return $response
            }
        }
        catch {
        }

        Start-Sleep -Seconds 3
    }

    throw "Timeout esperando health endpoint: $Url"
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
Set-Location $repoRoot

$composeFile = Join-Path $repoRoot "docker-compose.saas.yml"
$envLocalFile = Join-Path $repoRoot $EnvFile

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker no esta disponible en PATH."
}

if (-not (Test-Path $envLocalFile)) {
    throw "No existe $EnvFile. Primero ejecuta .\scripts\saas-up.ps1"
}

$webPort = Get-EnvSetting -FilePath $envLocalFile -Key "WEB_EXTERNAL_PORT" -DefaultValue "18000"
$healthUrl = "http://127.0.0.1:$webPort/api/v1/health/"

if ($Pull) {
    Write-Step "Actualizando imagenes remotas"
    Invoke-Compose -ComposeArgs @("-f", $composeFile, "--env-file", $envLocalFile, "pull")
}

if ($RestartOnly) {
    Write-Step "Reiniciando stack SaaS"
    Invoke-Compose -ComposeArgs @("-f", $composeFile, "--env-file", $envLocalFile, "restart")
}
else {
    $composeArgs = @("-f", $composeFile, "--env-file", $envLocalFile, "up", "-d")
    if (-not $NoBuild) {
        $composeArgs += "--build"
    }

    Write-Step "Aplicando actualizacion del stack SaaS"
    Invoke-Compose -ComposeArgs $composeArgs
}

Write-Step "Estado actual de servicios"
Invoke-Compose -ComposeArgs @("-f", $composeFile, "--env-file", $envLocalFile, "ps")

Write-Step "Esperando salud HTTP en $healthUrl"
$response = Wait-ForHealthEndpoint -Url $healthUrl -TimeoutSeconds $TimeoutSeconds
Write-Host ("Health OK: " + ($response | ConvertTo-Json -Compress)) -ForegroundColor Green

Write-Step "Actualizacion completada"
Write-Host "Web: http://127.0.0.1:$webPort/api/v1/health/"
Write-Host "Swagger: http://127.0.0.1:$webPort/api/docs/"