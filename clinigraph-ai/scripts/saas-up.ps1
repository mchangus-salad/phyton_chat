param(
    [string]$EnvFile = ".env.saas.local",
    [switch]$SkipBuild,
    [switch]$SkipHealthCheck,
    [int]$TimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"

$createdEnvFile = $false

function Write-Step {
    param([string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Cyan
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

function Set-EnvSetting {
    param(
        [string]$FilePath,
        [string]$Key,
        [string]$Value
    )

    $content = @()
    if (Test-Path $FilePath) {
        $content = Get-Content $FilePath
    }

    $updated = $false
    for ($i = 0; $i -lt $content.Length; $i++) {
        if ($content[$i] -match "^$Key=") {
            $content[$i] = "$Key=$Value"
            $updated = $true
            break
        }
    }

    if (-not $updated) {
        $content += "$Key=$Value"
    }

    Set-Content -Path $FilePath -Value $content
}

function New-RandomToken {
    param([int]$Length = 32)

    $alphabet = ((65..90) + (97..122) + (48..57))
    return -join ($alphabet | Get-Random -Count $Length | ForEach-Object { [char]$_ })
}

function Ensure-EnvValue {
    param(
        [string]$FilePath,
        [string]$Key,
        [string[]]$InvalidValues,
        [ScriptBlock]$Generator,
        [string]$Description
    )

    $currentValue = Get-EnvSetting -FilePath $FilePath -Key $Key -DefaultValue ""
    if (-not [string]::IsNullOrWhiteSpace($currentValue) -and ($InvalidValues -notcontains $currentValue)) {
        return $currentValue
    }

    $newValue = & $Generator
    Set-EnvSetting -FilePath $FilePath -Key $Key -Value $newValue
    Write-Host "Configured $Description in $FilePath"
    return $newValue
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
$envExampleFile = Join-Path $repoRoot ".env.saas.example"
$envLocalFile = Join-Path $repoRoot $EnvFile

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker no esta disponible en PATH."
}

Write-Step "Preparando entorno SaaS de CliniGraph AI"

if (-not (Test-Path $envLocalFile)) {
    if (-not (Test-Path $envExampleFile)) {
        throw "No existe .env.saas.example para crear el entorno local."
    }

    Copy-Item $envExampleFile $envLocalFile
    $createdEnvFile = $true
    Write-Host "Created $EnvFile from .env.saas.example"
}

$null = Ensure-EnvValue -FilePath $envLocalFile -Key "DJANGO_SECRET_KEY" -InvalidValues @("", "change-me-long-random-secret") -Generator { "django-$(New-RandomToken -Length 48)" } -Description "DJANGO_SECRET_KEY"
$null = Ensure-EnvValue -FilePath $envLocalFile -Key "AGENT_API_KEY" -InvalidValues @("", "change-me-api-key") -Generator { "saas-agent-$(New-RandomToken -Length 32)" } -Description "AGENT_API_KEY"

if ($createdEnvFile) {
    Write-Host "Using default DJANGO_DB_PASSWORD from .env.saas.example. Change it manually before production if needed."
}

$webPort = Get-EnvSetting -FilePath $envLocalFile -Key "WEB_EXTERNAL_PORT" -DefaultValue "18000"
$healthUrl = "http://127.0.0.1:$webPort/api/v1/health/"

$composeArgs = @("-f", $composeFile, "--env-file", $envLocalFile, "up", "-d")
if (-not $SkipBuild) {
    $composeArgs += "--build"
}

Write-Step "Construyendo y levantando stack SaaS"
Invoke-Compose -ComposeArgs $composeArgs

Write-Step "Estado actual de servicios"
Invoke-Compose -ComposeArgs @("-f", $composeFile, "--env-file", $envLocalFile, "ps")

if (-not $SkipHealthCheck) {
    Write-Step "Esperando salud HTTP en $healthUrl"
    $response = Wait-ForHealthEndpoint -Url $healthUrl -TimeoutSeconds $TimeoutSeconds
    Write-Host ("Health OK: " + ($response | ConvertTo-Json -Compress)) -ForegroundColor Green
}

Write-Step "Servicio listo"
Write-Host "Web: http://127.0.0.1:$webPort/api/v1/health/"
Write-Host "Swagger: http://127.0.0.1:$webPort/api/docs/"
Write-Host "Para actualizar sin limpiar: .\scripts\saas-refresh.ps1"
Write-Host "Para apagar y limpiar: .\scripts\saas-down.ps1"