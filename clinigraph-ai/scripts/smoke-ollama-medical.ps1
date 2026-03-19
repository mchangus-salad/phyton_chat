param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$Domain = "cardiology",
    [string]$Subdomain = "heart-failure",
    [string]$Condition = "heart failure",
    [string]$Marker = "NT-proBNP",
    [string]$EvidenceType = "guideline",
    [string]$Question = "Summarize key heart failure markers from available context.",
    [string]$ApiKey = ""
)

$ErrorActionPreference = "Stop"

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

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$envFile = Join-Path $repoRoot ".env.agentai.local"
$sampleCorpus = Join-Path $repoRoot "data\medical_sample_cardiology.json"
$ollamaExe = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"

if (-not (Test-Path $venvPython)) {
    Write-Fail "Virtual environment not found. Run .\scripts\dev-up.ps1 first."
}

if (-not (Test-Path $sampleCorpus)) {
    Write-Fail "Sample corpus not found at $sampleCorpus"
}

Set-Location $repoRoot

Write-Step "1/5 Verify Ollama availability"
if (-not (Test-Path $ollamaExe) -and -not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Fail "Ollama executable was not found. Install from https://ollama.com/download/windows"
}

try {
    $tags = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:11434/api/tags"
    Write-Ok "Ollama API is available. Models found: $($tags.models.Count)"
}
catch {
    Write-Fail "Ollama API is not available at http://127.0.0.1:11434"
}

Write-Step "2/5 Verify API health"
try {
    $health = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/health/"
    if ($health.status -ne "ok") {
        Write-Fail "Unexpected health status: $($health.status)"
    }
    Write-Ok "Django API is healthy"
}
catch {
    Write-Fail "Django API is unreachable at $BaseUrl. Start it with .venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000"
}

Write-Step "3/5 Import medical corpus"
& $venvPython manage.py import_medical_corpus $sampleCorpus --domain $Domain --subdomain $Subdomain
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Medical corpus import failed"
}
Write-Ok "Corpus imported into domain $Domain and subdomain $Subdomain"

if ([string]::IsNullOrWhiteSpace($ApiKey)) {
    $ApiKey = Get-EnvSetting -FilePath $envFile -Key "AGENT_API_KEY"
}
if ([string]::IsNullOrWhiteSpace($ApiKey)) {
    Write-Fail "No API key found. Set AGENT_API_KEY in .env.agentai.local or pass -ApiKey"
}
$headers = @{ "X-API-Key" = $ApiKey; "Content-Type" = "application/json" }

Write-Step "4/5 Run medical evidence search"
$evidenceBody = @{
    domain = $Domain
    subdomain = $Subdomain
    query = "heart failure marker evidence"
    condition = $Condition
    marker = $Marker
    evidence_type = $EvidenceType
    publication_year_from = 2020
    publication_year_to = 2026
    rerank = $true
    max_results = 3
} | ConvertTo-Json

$evidenceResponse = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/agent/medical/evidence/" -Headers $headers -Body $evidenceBody
if (-not $evidenceResponse) {
    Write-Fail "No response from medical evidence endpoint"
}
Write-Ok "Medical evidence endpoint returned $($evidenceResponse.evidence.Count) document(s)"

Write-Step "5/5 Run medical query"
$queryBody = @{
    domain = $Domain
    subdomain = $Subdomain
    question = $Question
    user_id = "smoke-ollama-medical"
} | ConvertTo-Json

$queryResponse = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/agent/medical/query/" -Headers $headers -Body $queryBody
if (-not $queryResponse -or [string]::IsNullOrWhiteSpace($queryResponse.answer)) {
    Write-Fail "No answer returned by medical query endpoint"
}
Write-Ok "Medical query endpoint returned an answer"

Write-Host "`n--- Smoke Result ---" -ForegroundColor Cyan
Write-Host "request_id (evidence): $($evidenceResponse.request_id)"
Write-Host "request_id (query)   : $($queryResponse.request_id)"
Write-Host "cache_hit            : $($queryResponse.cache_hit)"
Write-Host "domain/subdomain     : $($queryResponse.domain)/$($queryResponse.subdomain)"
Write-Host "first evidence id    : $($evidenceResponse.evidence[0].citation_id)"
Write-Host "---------------------" -ForegroundColor Cyan
Write-Host "CliniGraph AI medical smoke test passed." -ForegroundColor Green
