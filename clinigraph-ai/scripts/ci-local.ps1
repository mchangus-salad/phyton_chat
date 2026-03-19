param(
    [switch]$SkipBootstrap,
    [switch]$SkipDocker,
    [switch]$SkipSeed,
    [switch]$UseApiKey,
    [switch]$RunDevDown,
    [int]$Port = 8012,
    [string]$Question = "What documents do you have available?"
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Magenta
}

function Wait-ForHttp {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 45
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-RestMethod -Method Get -Uri $Url
            if ($response.status -eq "ok") {
                return
            }
        }
        catch {
        }
        Start-Sleep -Seconds 1
    }

    throw "Timeout waiting for service health at $Url"
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$devUpScript = Join-Path $scriptDir "dev-up.ps1"
$devDownScript = Join-Path $scriptDir "dev-down.ps1"
$quickTestScript = Join-Path $scriptDir "quick-test.ps1"

if (-not (Test-Path $venvPython)) {
    throw "Virtual environment not found. Run .\scripts\dev-up.ps1 first."
}

Set-Location $repoRoot

$serverProc = $null
try {
    if (-not $SkipBootstrap) {
        Write-Step "Running bootstrap (dev-up)"
        $devUpArgs = @("-NoServer")
        if ($SkipDocker) {
            $devUpArgs += "-SkipDocker"
        }
        if ($SkipSeed) {
            $devUpArgs += "-SkipSeed"
        }

        & $devUpScript @devUpArgs
        if ($LASTEXITCODE -ne 0) {
            throw "dev-up failed"
        }
    }

    Write-Step "Starting temporary Django server on 127.0.0.1:$Port"
    $serverProc = Start-Process -FilePath $venvPython `
        -ArgumentList @("manage.py", "runserver", "127.0.0.1:$Port", "--noreload") `
        -PassThru -WindowStyle Hidden -WorkingDirectory $repoRoot

    Wait-ForHttp -Url "http://127.0.0.1:$Port/api/v1/health/"

    Write-Step "Running quick-test"
    if ($UseApiKey) {
        & $quickTestScript -BaseUrl "http://127.0.0.1:$Port" -Question $Question -UseApiKey
    }
    else {
        & $quickTestScript -BaseUrl "http://127.0.0.1:$Port" -Question $Question
    }

    if ($LASTEXITCODE -ne 0) {
        throw "quick-test failed"
    }

    Write-Step "CI local flow finished successfully"
}
finally {
    if ($serverProc -and -not $serverProc.HasExited) {
        Write-Step "Stopping temporary Django server"
        Stop-Process -Id $serverProc.Id -Force
    }

    if ($RunDevDown) {
        Write-Step "Stopping local Docker stack (dev-down)"
        & $devDownScript
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "dev-down finished with errors"
        }
    }
}
