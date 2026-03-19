param(
    [string]$Path = ".\data\oncology_sample.json",
    [string]$Domain = "oncology",
    [string]$Subdomain = ""
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    throw "Virtual environment not found. Run .\scripts\dev-up.ps1 first."
}

Set-Location $repoRoot
$args = @("manage.py", "import_oncology_corpus", $Path, "--domain", $Domain)
if ($Subdomain) {
    $args += @("--subdomain", $Subdomain)
}

& $venvPython @args
if ($LASTEXITCODE -ne 0) {
    throw "Oncology import failed."
}
