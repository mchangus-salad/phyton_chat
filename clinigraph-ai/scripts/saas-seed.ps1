param(
    [string[]]$Domains = @(),
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Invoke-DockerExec {
    param(
        [string[]]$Args
    )

    if ($DryRun) {
        Write-Host "[dry-run] docker exec clinigraph-web $($Args -join ' ')"
        return
    }

    & docker exec clinigraph-web @Args
    if ($LASTEXITCODE -ne 0) {
        throw "Fallo ejecutando docker exec clinigraph-web $($Args -join ' ')"
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
Set-Location $repoRoot

$containerRunning = docker ps --filter "name=^clinigraph-web$" --format "{{.Names}}"
if (-not $containerRunning) {
    throw "No se encontro el contenedor clinigraph-web en ejecucion. Ejecuta .\\scripts\\saas-up.ps1 primero."
}

$normalizedDomains = @($Domains | ForEach-Object { $_.Trim().ToLower() } | Where-Object { $_ })

$seedPlan = @(
    @{ Domain = "oncology"; File = "/app/data/seed_oncology.json"; Command = "import_oncology_corpus"; Extra = @("--domain", "oncology") },
    @{ Domain = "cardiology"; File = "/app/data/seed_cardiology.json"; Command = "import_medical_corpus"; Extra = @("--domain", "cardiology") },
    @{ Domain = "neurology"; File = "/app/data/seed_neurology.json"; Command = "import_medical_corpus"; Extra = @("--domain", "neurology") },
    @{ Domain = "endocrinology"; File = "/app/data/seed_endocrinology.json"; Command = "import_medical_corpus"; Extra = @("--domain", "endocrinology") },
    @{ Domain = "pulmonology"; File = "/app/data/seed_pulmonology.json"; Command = "import_medical_corpus"; Extra = @("--domain", "pulmonology") },
    @{ Domain = "rheumatology"; File = "/app/data/seed_rheumatology.json"; Command = "import_medical_corpus"; Extra = @("--domain", "rheumatology") },
    @{ Domain = "infectious-diseases"; File = "/app/data/seed_infectious_diseases.json"; Command = "import_medical_corpus"; Extra = @("--domain", "infectious-diseases") },
    @{ Domain = "gastroenterology"; File = "/app/data/seed_gastroenterology.json"; Command = "import_medical_corpus"; Extra = @("--domain", "gastroenterology") },
    @{ Domain = "hematology"; File = "/app/data/seed_hematology.json"; Command = "import_medical_corpus"; Extra = @("--domain", "hematology") }
)

if ($normalizedDomains.Count -gt 0) {
    $seedPlan = @($seedPlan | Where-Object { $normalizedDomains -contains $_.Domain.ToLower() })
    if ($seedPlan.Count -eq 0) {
        throw "No hay dominios validos para sembrar. Dominios disponibles: oncology, cardiology, neurology, endocrinology, pulmonology, rheumatology, infectious-diseases, gastroenterology, hematology."
    }
}

Write-Step "Importando corpus inicial en contenedor SaaS"

$success = 0
$failed = 0

foreach ($item in $seedPlan) {
    $args = @("python", "manage.py", $item.Command, $item.File) + $item.Extra
    Write-Host "- [$($item.Domain)] $($item.Command) $($item.File)"

    try {
        Invoke-DockerExec -Args $args
        $success += 1
    }
    catch {
        $failed += 1
        Write-Host "  ERROR: $($_.Exception.Message)" -ForegroundColor Red
    }
}

Write-Step "Seed finalizado"
Write-Host "Exitosos: $success"
Write-Host "Fallidos: $failed"

if ($failed -gt 0) {
    throw "El seed termino con errores."
}
