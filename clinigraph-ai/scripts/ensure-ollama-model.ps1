param(
    [Parameter(Mandatory = $true)]
    [string]$EnvFile,
    [Parameter(Mandatory = $true)]
    [string]$ContainerName
)

$ErrorActionPreference = "Stop"

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

function Wait-ForOllamaApi {
    param([string]$ContainerName)

    $deadline = (Get-Date).AddMinutes(5)
    while ((Get-Date) -lt $deadline) {
        try {
            & docker exec $ContainerName ollama list | Out-Null
            if ($LASTEXITCODE -eq 0) {
                return
            }
        }
        catch {
        }
        Start-Sleep -Seconds 3
    }

    throw "Ollama no respondio en el contenedor $ContainerName"
}

$provider = (Get-EnvSetting -FilePath $EnvFile -Key "AGENT_LLM_PROVIDER" -DefaultValue "mock").ToLower()
if ($provider -ne "ollama") {
    Write-Host "Ollama model pull skipped because AGENT_LLM_PROVIDER=$provider"
    exit 0
}

$autoPull = (Get-EnvSetting -FilePath $EnvFile -Key "OLLAMA_MODEL_AUTO_PULL" -DefaultValue "true").ToLower()
if ($autoPull -ne "true") {
    Write-Host "Ollama model pull skipped because OLLAMA_MODEL_AUTO_PULL=$autoPull"
    exit 0
}

$model = Get-EnvSetting -FilePath $EnvFile -Key "AGENT_LLM_MODEL" -DefaultValue "llama3.1:8b"
if ([string]::IsNullOrWhiteSpace($model)) {
    throw "AGENT_LLM_MODEL no esta configurado en $EnvFile"
}

Write-Step "Esperando servicio Ollama"
Wait-ForOllamaApi -ContainerName $ContainerName

Write-Step "Asegurando modelo Ollama: $model"
& docker exec $ContainerName ollama pull $model
if ($LASTEXITCODE -ne 0) {
    throw "Fallo al descargar modelo Ollama '$model' en $ContainerName"
}

Write-Host "Modelo Ollama listo: $model" -ForegroundColor Green
