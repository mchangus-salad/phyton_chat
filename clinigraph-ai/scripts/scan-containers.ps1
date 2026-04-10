param(
    [string]$Image = '',
    [string]$Severity = 'CRITICAL,HIGH',
    [switch]$ExitOnFinding,
    [switch]$JsonOutput,
    [string]$OutputFile = ''
)

<#
.SYNOPSIS
    Run Trivy container image scanning against the CliniGraph AI web image.

.DESCRIPTION
    Downloads and runs Trivy (aquasecurity/trivy) via Docker to scan the
    built clinigraph-ai-web image for known CVEs. Intended to run as a
    pre-deploy gate in CI or as a local developer check.

.PARAMETER Image
    Docker image to scan. Defaults to 'clinigraph-ai-web:latest'.

.PARAMETER Severity
    Comma-separated severity levels to report. Default: 'CRITICAL,HIGH'.

.PARAMETER ExitOnFinding
    If set, exits with code 1 when any finding at or above the specified
    severity is detected. Use this in CI pipelines to block deploys.

.PARAMETER JsonOutput
    If set, outputs Trivy results as JSON. Useful for SIEM ingestion.

.PARAMETER OutputFile
    Optional file path to write the Trivy report. If omitted, output goes to stdout.

.EXAMPLE
    .\scripts\scan-containers.ps1 -ExitOnFinding
    .\scripts\scan-containers.ps1 -JsonOutput -OutputFile trivy-report.json
    .\scripts\scan-containers.ps1 -Image clinigraph-ai-web:v1.2.0 -Severity CRITICAL
#>

$ErrorActionPreference = 'Stop'
$scriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot    = Split-Path -Parent $scriptDir
$targetImage = if ($Image) { $Image } else { 'clinigraph-ai-web:latest' }

function Write-Step {
    param([string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

# ── Ensure Docker is available ─────────────────────────────────────────────────
Write-Step "Checking Docker availability"
try {
    $null = & docker info 2>&1
} catch {
    throw "Docker is not running or not installed. Cannot perform container scan."
}

# ── Build image if it doesn't exist locally ────────────────────────────────────
Write-Step "Verifying target image: $targetImage"
$imageExists = & docker images -q $targetImage 2>$null
if (-not $imageExists) {
    Write-Step "Image not found locally. Building from Dockerfile..."
    Set-Location $repoRoot
    & docker build -t $targetImage -f Dockerfile .
    if ($LASTEXITCODE -ne 0) {
        throw "Docker build failed for $targetImage"
    }
}

# ── Run Trivy scan ─────────────────────────────────────────────────────────────
Write-Step "Running Trivy scan (severity: $Severity)"

$trivyArgs = @(
    'run', '--rm',
    '-v', '/var/run/docker.sock:/var/run/docker.sock:ro',
    'aquasec/trivy:latest',
    'image',
    '--severity', $Severity,
    '--no-progress'
)

if ($JsonOutput) {
    $trivyArgs += @('--format', 'json')
}

$trivyArgs += $targetImage

if ($OutputFile) {
    $report = & docker @trivyArgs 2>&1
    $exitCode = $LASTEXITCODE
    $resolvedPath = Join-Path $repoRoot $OutputFile
    $report | Out-File -FilePath $resolvedPath -Encoding utf8
    Write-Host "Report saved to: $resolvedPath"
} else {
    & docker @trivyArgs
    $exitCode = $LASTEXITCODE
}

# ── Evaluate result ────────────────────────────────────────────────────────────
if ($exitCode -ne 0 -and $ExitOnFinding) {
    Write-Host "`n[SCAN FAILED] Trivy found vulnerabilities at severity: $Severity" -ForegroundColor Red
    Write-Host "Fix the findings before deploying. See docs/CONTAINER_SCANNING.md for guidance." -ForegroundColor Red
    exit 1
} elseif ($exitCode -ne 0) {
    Write-Host "`n[SCAN WARNING] Trivy found vulnerabilities at severity: $Severity" -ForegroundColor Yellow
    Write-Host "Review the report and update dependencies as needed." -ForegroundColor Yellow
    exit 0
} else {
    Write-Host "`n[SCAN PASSED] No $Severity vulnerabilities found in $targetImage" -ForegroundColor Green
    exit 0
}
