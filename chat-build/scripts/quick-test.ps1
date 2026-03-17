param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$Username = "quicktest",
    [string]$Password = "quicktest-pass123!",
    [string]$Question = "What documents do you have available?",
    [switch]$UseApiKey
)

$ErrorActionPreference = "Stop"

# ── helpers ─────────────────────────────────────────────────────────────────

function Write-Step {
    param([string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-Host "    OK  $Message" -ForegroundColor Green
}

function Write-Fail {
    param([string]$Message)
    Write-Host "    FAIL $Message" -ForegroundColor Red
    exit 1
}

function Get-EnvSetting {
    param([string]$FilePath, [string]$Key, [string]$DefaultValue = "")
    if (-not (Test-Path $FilePath)) { return $DefaultValue }
    $line = Get-Content $FilePath | Where-Object { $_ -match "^$Key=" } | Select-Object -First 1
    if (-not $line) { return $DefaultValue }
    $value = $line.Substring($Key.Length + 1).Trim()
    return ($value -eq "") ? $DefaultValue : $value
}

# ── setup ────────────────────────────────────────────────────────────────────

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot  = Split-Path -Parent $scriptDir
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$envFile    = Join-Path $repoRoot ".env.agentai.local"

if (-not (Test-Path $venvPython)) {
    Write-Fail "Virtual environment not found. Run .\scripts\dev-up.ps1 first."
}

Set-Location $repoRoot

# ── step 1: health check ─────────────────────────────────────────────────────

Write-Step "1/4  Health check"
try {
    $health = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/health/"
    if ($health.status -ne "ok") { Write-Fail "Health returned unexpected status: $($health.status)" }
    Write-Ok "/api/v1/health/ => status=$($health.status)"
} catch {
    Write-Fail "Server not reachable at $BaseUrl. Start it with: .venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000"
}

# ── step 2: create / ensure test user ────────────────────────────────────────

Write-Step "2/4  Ensure test user ($Username)"
& $venvPython manage.py shell -c @"
from django.contrib.auth import get_user_model
User = get_user_model()
user, created = User.objects.get_or_create(username='$Username', defaults={'email': ''})
user.set_password('$Password')
user.save()
print('ready')
"@

if ($LASTEXITCODE -ne 0) { Write-Fail "Could not create test user." }
Write-Ok "User $Username is ready."

# ── step 3: obtain auth header ────────────────────────────────────────────────

if ($UseApiKey) {
    Write-Step "3/4  Using X-API-Key from .env.agentai.local"
    $apiKey = Get-EnvSetting -FilePath $envFile -Key "AGENT_API_KEY"
    if ([string]::IsNullOrWhiteSpace($apiKey)) {
        Write-Fail "AGENT_API_KEY is not set in .env.agentai.local"
    }
    $authHeader = @{ "X-API-Key" = $apiKey }
    Write-Ok "X-API-Key loaded (length=$($apiKey.Length))."
} else {
    Write-Step "3/4  Obtaining JWT bearer token"
    $tokenBody    = @{ username = $Username; password = $Password } | ConvertTo-Json
    $tokenResponse = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/auth/token/" `
        -ContentType "application/json" -Body $tokenBody
    $accessToken  = $tokenResponse.access
    if ([string]::IsNullOrWhiteSpace($accessToken)) {
        Write-Fail "Token endpoint did not return an access token."
    }
    $authHeader = @{ Authorization = "Bearer $accessToken" }
    Write-Ok "JWT access token obtained (length=$($accessToken.Length))."
}

# ── step 4: call agent endpoint ───────────────────────────────────────────────

Write-Step "4/4  Calling /api/v1/agent/query/"
$body = @{ question = $Question; user_id = "quick-test" } | ConvertTo-Json
$response = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/agent/query/" `
    -ContentType "application/json" -Headers $authHeader -Body $body

Write-Ok "Response received."

Write-Host "`n--- Result ---" -ForegroundColor Cyan
Write-Host "  request_id : $($response.request_id)"
Write-Host "  cache_hit  : $($response.cache_hit)"
Write-Host "  answer     : $($response.answer)"
Write-Host "--------------" -ForegroundColor Cyan
Write-Host "`nQuick test passed." -ForegroundColor Green
