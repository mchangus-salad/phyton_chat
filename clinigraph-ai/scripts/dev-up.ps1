param(
    [switch]$NoServer,
    [switch]$RecreateVenv,
    [switch]$SkipDocker,
    [switch]$SkipSmokeTest,
    [switch]$SkipSeed
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Get-BasePython {
    if ($env:LOCAL_PYTHON_EXE -and (Test-Path $env:LOCAL_PYTHON_EXE)) {
        return @($env:LOCAL_PYTHON_EXE)
    }

    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        try {
            & py -3.14 -c "import sys" | Out-Null
            return @("py", "-3.14")
        }
        catch {
            return @("py")
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @($python.Source)
    }

    throw "No se encontro Python. Instala Python 3.14+ o define LOCAL_PYTHON_EXE."
}

function Invoke-CheckedCommand {
    param(
        [string[]]$Command,
        [string]$Description
    )

    Write-Step $Description
    & $Command[0] @($Command[1..($Command.Length - 1)])
    if ($LASTEXITCODE -ne 0) {
        throw "Fallo: $Description"
    }
}

function Wait-ForTcpPort {
    param(
        [string]$Address,
        [int]$Port,
        [int]$TimeoutSeconds = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $client = New-Object System.Net.Sockets.TcpClient
            $async = $client.BeginConnect($Address, $Port, $null, $null)
            $connected = $async.AsyncWaitHandle.WaitOne(1000, $false)
            if ($connected -and $client.Connected) {
                $client.EndConnect($async)
                $client.Close()
                return
            }
            $client.Close()
        }
        catch {
        }
        Start-Sleep -Seconds 1
    }

    throw "Timeout esperando puerto $Address`:$Port"
}

function Get-EnvSetting {
    param(
        [string]$FilePath,
        [string]$Key,
        [string]$DefaultValue
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

    if (-not (Test-Path $FilePath)) {
        Set-Content -Path $FilePath -Value "$Key=$Value"
        return
    }

    $content = Get-Content $FilePath
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

function Ensure-AgentApiKey {
    param(
        [string]$EnvFile
    )

    $currentKey = Get-EnvSetting -FilePath $EnvFile -Key "AGENT_API_KEY" -DefaultValue ""
    if (-not [string]::IsNullOrWhiteSpace($currentKey)) {
        return $currentKey
    }

    # Generate a durable local API key so agent endpoint is protected by default.
    $randomPart = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 24 | ForEach-Object { [char]$_ })
    $newKey = "local-agent-$randomPart"
    Set-EnvSetting -FilePath $EnvFile -Key "AGENT_API_KEY" -Value $newKey
    Write-Host "Generated AGENT_API_KEY in .env.agentai.local"
    return $newKey
}

function Initialize-WeaviateSchema {
    param(
        [string]$EnvFile
    )

    $weaviateHost = Get-EnvSetting -FilePath $EnvFile -Key "WEAVIATE_HTTP_HOST" -DefaultValue "127.0.0.1"
    $weaviatePort = Get-EnvSetting -FilePath $EnvFile -Key "WEAVIATE_HTTP_PORT" -DefaultValue "8088"
    $weaviateIndex = Get-EnvSetting -FilePath $EnvFile -Key "WEAVIATE_INDEX" -DefaultValue "AgentDocuments"
    $baseUrl = "http://$weaviateHost`:$weaviatePort"

    Write-Step "Inicializando esquema Weaviate ($weaviateIndex)"

    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        try {
            Invoke-RestMethod -Method Get -Uri "$baseUrl/v1/meta" | Out-Null
            $ready = $true
            break
        }
        catch {
            Start-Sleep -Seconds 2
        }
    }

    if (-not $ready) {
        throw "Weaviate no respondio en /v1/meta despues de esperar readiness."
    }

    $schema = Invoke-RestMethod -Method Get -Uri "$baseUrl/v1/schema"
    $classes = @()
    if ($schema -and $schema.classes) {
        $classes = @($schema.classes | ForEach-Object { $_.class })
    }

    if ($classes -contains $weaviateIndex) {
        Write-Host "Coleccion Weaviate ya existe: $weaviateIndex"
        return
    }

    $body = @{
        class = $weaviateIndex
        description = "Collection for AgentAI local RAG documents"
        vectorizer = "none"
        properties = @(
            @{
                name = "text"
                dataType = @("text")
            }
            @{
                name = "source"
                dataType = @("text")
            }
            @{
                name = "created_at"
                dataType = @("date")
            }
        )
    } | ConvertTo-Json -Depth 10

    Invoke-RestMethod -Method Post -Uri "$baseUrl/v1/schema" -ContentType "application/json" -Body $body | Out-Null
    Write-Host "Coleccion Weaviate creada: $weaviateIndex"
}

function Ensure-OllamaModel {
    param([string]$EnvFile)

    $ollamaContainer = Get-EnvSetting -FilePath $EnvFile -Key "OLLAMA_CONTAINER_NAME" -DefaultValue "agentai-ollama"
    & "$scriptDir\ensure-ollama-model.ps1" -EnvFile $EnvFile -ContainerName $ollamaContainer
    if ($LASTEXITCODE -ne 0) {
        throw "Fallo ensure-ollama-model.ps1"
    }
}

function Invoke-DjangoSmokeTest {
    param(
        [string]$PythonExe,
        [string]$RepoPath,
        [int]$Port = 8010
    )

    Write-Step "Ejecutando smoke test HTTP de Django (/api/health/)"
    $serverProc = $null
    try {
        $serverProc = Start-Process -FilePath $PythonExe -ArgumentList @("manage.py", "runserver", "127.0.0.1:$Port", "--noreload") -PassThru -WindowStyle Hidden -WorkingDirectory $RepoPath

        Wait-ForTcpPort -Address "127.0.0.1" -Port $Port -TimeoutSeconds 60
        $response = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:$Port/api/health/"
        if (-not $response -or $response.status -ne "ok") {
            throw "Smoke test devolvio respuesta inesperada en /api/health/."
        }

        Write-Host "Smoke test OK: /api/health/"
    }
    finally {
        if ($serverProc -and -not $serverProc.HasExited) {
            Stop-Process -Id $serverProc.Id -Force
        }
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
Set-Location $repoRoot

$composeFile = Join-Path $repoRoot "docker-compose.local.yml"
$envLocalFile = Join-Path $repoRoot ".env.agentai.local"
$envExampleFile = Join-Path $repoRoot ".env.agentai.example"
$venvDir = Join-Path $repoRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$requirementsFile = Join-Path $repoRoot "api\requirements-agentai.txt"

Write-Step "Bootstrap local de CliniGraph AI"

if (-not (Test-Path $envLocalFile)) {
    Write-Step "Creating .env.agentai.local from .env.agentai.example"
    Copy-Item $envExampleFile $envLocalFile
}

$agentApiKey = Ensure-AgentApiKey -EnvFile $envLocalFile

$basePython = Get-BasePython

if ($RecreateVenv -and (Test-Path $venvDir)) {
    Write-Step "Eliminando .venv existente"
    Remove-Item -Recurse -Force $venvDir
}

if (-not (Test-Path $venvPython)) {
    Invoke-CheckedCommand -Command ($basePython + @("-m", "venv", $venvDir)) -Description "Creando entorno virtual .venv"
}

Invoke-CheckedCommand -Command @($venvPython, "-m", "pip", "install", "--upgrade", "pip") -Description "Actualizando pip"
Invoke-CheckedCommand -Command @($venvPython, "-m", "pip", "install", "-r", $requirementsFile) -Description "Instalando dependencias Python"

if (-not $SkipDocker) {
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $docker) {
        throw "Docker no esta disponible. Instala Docker Desktop o usa -SkipDocker."
    }

    Invoke-CheckedCommand -Command @("docker", "compose", "-f", $composeFile, "up", "-d") -Description "Levantando Redis, Kafka, Weaviate y Ollama"

    Write-Step "Esperando Redis, Kafka, Weaviate y Ollama"
    Wait-ForTcpPort -Address "127.0.0.1" -Port 6379 -TimeoutSeconds 60
    Wait-ForTcpPort -Address "127.0.0.1" -Port 9094 -TimeoutSeconds 120
    Wait-ForTcpPort -Address "127.0.0.1" -Port 8088 -TimeoutSeconds 120
    Wait-ForTcpPort -Address "127.0.0.1" -Port 11434 -TimeoutSeconds 180
    Initialize-WeaviateSchema -EnvFile $envLocalFile
    Ensure-OllamaModel -EnvFile $envLocalFile
}

Invoke-CheckedCommand -Command @($venvPython, "manage.py", "migrate") -Description "Aplicando migraciones"
Invoke-CheckedCommand -Command @($venvPython, "manage.py", "seed_subscription_plans") -Description "Sembrando planes de suscripcion"
Invoke-CheckedCommand -Command @($venvPython, "manage.py", "check") -Description "Validando proyecto Django"

if (-not $SkipSeed) {
    Invoke-CheckedCommand -Command @($venvPython, "manage.py", "seed_weaviate") -Description "Cargando datos semilla en Weaviate"
}

if (-not $SkipSmokeTest) {
    Invoke-DjangoSmokeTest -PythonExe $venvPython -RepoPath $repoRoot
}

Write-Step "Entorno listo"
Write-Host ".venv: $venvDir"
Write-Host "Redis: redis://127.0.0.1:6379/0"
Write-Host "Kafka: 127.0.0.1:9094"
Write-Host "Kafka UI: http://127.0.0.1:8085"
Write-Host "Weaviate: http://127.0.0.1:8088"
Write-Host "Ollama: http://127.0.0.1:11434"
Write-Host "Django health: http://127.0.0.1:8000/api/health/"
Write-Host "Agent API key configured in .env.agentai.local (AGENT_API_KEY)."

$envFileContent = if (Test-Path $envLocalFile) { Get-Content $envLocalFile -Raw } else { "" }
$hasOpenAIKey = $env:OPENAI_API_KEY -or ($envFileContent -match "(?m)^OPENAI_API_KEY=.+$")
$hasAnthropicKey = $env:ANTHROPIC_API_KEY -or ($envFileContent -match "(?m)^ANTHROPIC_API_KEY=.+$")
$llmProvider = (Get-EnvSetting -FilePath $envLocalFile -Key "AGENT_LLM_PROVIDER" -DefaultValue "gpt").ToLower()
$isSandboxProvider = $llmProvider -in @("mock", "sandbox")

if (-not $isSandboxProvider -and -not $hasOpenAIKey -and -not $hasAnthropicKey) {
    Write-Warning "No hay OPENAI_API_KEY ni ANTHROPIC_API_KEY en el entorno actual o en .env.agentai.local. El endpoint del agente no generara respuestas reales del LLM hasta configurarlo."
}

if ($NoServer) {
    Write-Step "Setup finalizado sin arrancar servidor"
    exit 0
}

Write-Step "Arrancando Django en http://127.0.0.1:8000"
& $venvPython manage.py runserver 127.0.0.1:8000