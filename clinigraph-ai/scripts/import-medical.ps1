param(
    [string]$Path = ".\data\medical_sample_cardiology.json",
    [string]$Domain = "cardiology",
    [string]$Subdomain = "",
    [ValidateSet("upsert", "batch-dedup", "versioned")]
    [string]$DedupMode = "upsert",
    [string]$VersionTag = ""
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    throw "Virtual environment not found. Run .\scripts\dev-up.ps1 first."
}

Set-Location $repoRoot
$args = @("manage.py", "import_medical_corpus", $Path, "--domain", $Domain, "--dedup-mode", $DedupMode)
if ($Subdomain) {
    $args += @("--subdomain", $Subdomain)
}
if ($VersionTag) {
    $args += @("--version-tag", $VersionTag)
}

& $venvPython @args
if ($LASTEXITCODE -ne 0) {
    throw "Medical import failed."
}
