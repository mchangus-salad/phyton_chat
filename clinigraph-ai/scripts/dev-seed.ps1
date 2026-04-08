$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Green
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
Set-Location $repoRoot

$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "No existe .venv. Ejecuta primero .\\scripts\\dev-up.ps1 -NoServer"
}

Write-Step "Sembrando datos iniciales en Weaviate"
& $venvPython manage.py seed_weaviate
if ($LASTEXITCODE -ne 0) {
    throw "Fallo al ejecutar seed_weaviate"
}

Write-Step "Importando corpus medico por especialidad"
$medicalCorpus = @(
    @{ file="data/seed_oncology.json";           domain="oncology" },
    @{ file="data/seed_cardiology.json";         domain="cardiology" },
    @{ file="data/seed_neurology.json";          domain="neurology" },
    @{ file="data/seed_endocrinology.json";      domain="endocrinology" },
    @{ file="data/seed_pulmonology.json";        domain="pulmonology" },
    @{ file="data/seed_rheumatology.json";       domain="rheumatology" },
    @{ file="data/seed_hematology.json";         domain="hematology" },
    @{ file="data/seed_gastroenterology.json";   domain="gastroenterology" },
    @{ file="data/seed_infectious_diseases.json";domain="infectious_diseases" }
)
foreach ($corpus in $medicalCorpus) {
    Write-Host "  -> $($corpus.domain)" -ForegroundColor Gray
    & $venvPython manage.py import_medical_corpus $corpus.file --domain $corpus.domain 2>&1 | Select-String "Imported|Error|Failed"
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Fallo al importar corpus $($corpus.domain), continuando..."
    }
}

Write-Step "Sembrando usuarios locales por rol"
& $venvPython manage.py seed_local_users
if ($LASTEXITCODE -ne 0) {
    throw "Fallo al ejecutar seed_local_users"
}

Write-Step "Seed completado"
