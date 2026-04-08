<#
.SYNOPSIS
    CliniGraph AI – unified cloud deployment script.

.DESCRIPTION
    Provisions infrastructure via Terraform and deploys the full application
    stack via Helm to AKS (Azure), GKE (GCP), or EKS (AWS).

.PARAMETER Provider
    Target cloud: azure | gcp | aws  (REQUIRED)

.PARAMETER Env
    Deployment environment: dev | prod  (REQUIRED)

.PARAMETER ImageTag
    Docker image tag to build and deploy. Default: latest

.PARAMETER Namespace
    Kubernetes namespace. Default: clinigraph

.PARAMETER ReleaseName
    Helm release name. Default: clinigraph

.PARAMETER GcpProjectId
    GCP project ID. Required when Provider=gcp.

.PARAMETER SkipTerraform
    Skip Terraform provisioning (assume infrastructure already exists).

.PARAMETER SkipBuild
    Skip Docker build + push (assume images already in registry).

.PARAMETER SkipHelm
    Skip Helm chart deployment.

.PARAMETER SkipSeed
    Skip waiting for the seed Job to complete (seed still runs; just not waited on).

.PARAMETER DryRun
    Print commands without executing them.

.EXAMPLE
    .\deploy.ps1 -Provider azure -Env dev
    .\deploy.ps1 -Provider gcp   -Env prod -GcpProjectId my-gcp-project -ImageTag v1.2.3
    .\deploy.ps1 -Provider aws   -Env dev  -SkipTerraform
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("azure", "gcp", "aws")]
    [string]$Provider,

    [Parameter(Mandatory = $true)]
    [ValidateSet("dev", "prod")]
    [string]$Env,

    [string]$ImageTag     = "latest",
    [string]$Namespace    = "clinigraph",
    [string]$ReleaseName  = "clinigraph",
    [string]$GcpProjectId = $env:GCP_PROJECT_ID,

    [switch]$SkipTerraform,
    [switch]$SkipBuild,
    [switch]$SkipHelm,
    [switch]$SkipSeed,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# ── Paths ─────────────────────────────────────────────────────────────────────
$InfraRoot  = $PSScriptRoot
$RepoRoot   = Split-Path -Parent $InfraRoot
$TfDir      = Join-Path $InfraRoot "terraform" $Provider
$HelmDir    = Join-Path $InfraRoot "helm" "clinigraph"
$FrontendDir = Join-Path $RepoRoot "frontend"

# ── Helpers ───────────────────────────────────────────────────────────────────
function Write-Step  ([string]$msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok    ([string]$msg) { Write-Host " OK  $msg" -ForegroundColor Green }
function Write-Warn  ([string]$msg) { Write-Host "WARN $msg" -ForegroundColor Yellow }
function Write-Fail  ([string]$msg) { Write-Host "FAIL $msg" -ForegroundColor Red; exit 1 }

function Invoke-Cmd {
    param([string[]]$Cmd)
    if ($DryRun) {
        Write-Host "  [dry-run] $($Cmd -join ' ')" -ForegroundColor DarkGray
        return ""
    }
    & $Cmd[0] $Cmd[1..($Cmd.Length - 1)]
    if ($LASTEXITCODE -ne 0) { Write-Fail "Command failed: $($Cmd -join ' ')" }
}

function Invoke-CmdOutput {
    param([string[]]$Cmd)
    if ($DryRun) { return "" }
    $out = & $Cmd[0] $Cmd[1..($Cmd.Length - 1)] 2>&1
    if ($LASTEXITCODE -ne 0) { Write-Fail "Command failed: $($Cmd -join ' ')" }
    return $out
}

function Require-Tool ([string]$name) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
        Write-Fail "'$name' is not installed or not in PATH."
    }
    Write-Ok "$name found"
}

# ── 1. Validate prerequisites ─────────────────────────────────────────────────
Write-Step "Checking prerequisites"
Require-Tool "terraform"
Require-Tool "helm"
Require-Tool "kubectl"
Require-Tool "docker"

switch ($Provider) {
    "azure" { Require-Tool "az" }
    "gcp"   {
        Require-Tool "gcloud"
        if (-not $GcpProjectId) { Write-Fail "GcpProjectId is required for provider=gcp. Set -GcpProjectId or GCP_PROJECT_ID env var." }
    }
    "aws"   { Require-Tool "aws" }
}

# ── 2. Bootstrap remote Terraform state backend ───────────────────────────────
if (-not $SkipTerraform) {
    Write-Step "Bootstrapping remote state backend ($Provider)"

    $StateContainer = "clinigraph-tfstate-$Env"

    switch ($Provider) {
        "azure" {
            $RgName  = "rg-clinigraph-tfstate"
            $SaName  = "clinigraphtfstate$($Env)sa"
            $SaExists = Invoke-CmdOutput @("az", "storage", "account", "check-name", "--name", $SaName, "--query", "nameAvailable", "-o", "tsv")
            if ($SaExists -match "true") {
                Write-Ok "Creating Azure storage account for Terraform state..."
                Invoke-Cmd @("az", "group", "create", "--name", $RgName, "--location", "eastus", "-o", "none")
                Invoke-Cmd @("az", "storage", "account", "create", "--name", $SaName, "--resource-group", $RgName, "--sku", "Standard_LRS", "-o", "none")
                Invoke-Cmd @("az", "storage", "container", "create", "--name", $StateContainer, "--account-name", $SaName, "-o", "none")
            } else {
                Write-Ok "Azure storage account $SaName already exists."
            }

            $BackendCfg = @"
resource_group_name  = "$RgName"
storage_account_name = "$SaName"
container_name       = "$StateContainer"
key                  = "terraform.tfstate"
"@
            $BackendFile = Join-Path $TfDir "backend.hcl"
            [System.IO.File]::WriteAllText($BackendFile, $BackendCfg)

            # Enable backend in providers.tf by removing comment marker
            $ProvidersFile = Join-Path $TfDir "providers.tf"
            (Get-Content $ProvidersFile) -replace "# backend `"azurerm`" \{\}", 'backend "azurerm" {}' |
                Set-Content $ProvidersFile
        }

        "gcp" {
            $BucketName = "clinigraph-tfstate-$Env-$GcpProjectId"
            $BucketExists = Invoke-CmdOutput @("gcloud", "storage", "buckets", "describe", "gs://$BucketName", "--project", $GcpProjectId, "--format", "value(name)") 2>&1
            if ($LASTEXITCODE -ne 0) {
                Write-Ok "Creating GCS bucket for Terraform state..."
                Invoke-Cmd @("gcloud", "storage", "buckets", "create", "gs://$BucketName", "--project", $GcpProjectId, "--location", "us-central1", "--uniform-bucket-level-access")
            } else {
                Write-Ok "GCS bucket $BucketName already exists."
            }

            $BackendCfg = @"
bucket = "$BucketName"
prefix = "terraform/$Env"
"@
            $BackendFile = Join-Path $TfDir "backend.hcl"
            [System.IO.File]::WriteAllText($BackendFile, $BackendCfg)

            $ProvidersFile = Join-Path $TfDir "providers.tf"
            (Get-Content $ProvidersFile) -replace "# backend `"gcs`" \{\}", 'backend "gcs" {}' |
                Set-Content $ProvidersFile
        }

        "aws" {
            $AccountId  = Invoke-CmdOutput @("aws", "sts", "get-caller-identity", "--query", "Account", "--output", "text")
            $BucketName = "clinigraph-tfstate-$Env-$AccountId"
            $TableName  = "clinigraph-tfstate-lock"
            $Region     = $env:AWS_DEFAULT_REGION
            if (-not $Region) { $Region = "us-east-1" }

            $BucketExists = Invoke-CmdOutput @("aws", "s3api", "head-bucket", "--bucket", $BucketName) 2>&1
            if ($LASTEXITCODE -ne 0) {
                Write-Ok "Creating S3 bucket for Terraform state..."
                if ($Region -eq "us-east-1") {
                    Invoke-Cmd @("aws", "s3api", "create-bucket", "--bucket", $BucketName, "--region", $Region)
                } else {
                    Invoke-Cmd @("aws", "s3api", "create-bucket", "--bucket", $BucketName, "--region", $Region, "--create-bucket-configuration", "LocationConstraint=$Region")
                }
                Invoke-Cmd @("aws", "s3api", "put-bucket-versioning", "--bucket", $BucketName, "--versioning-configuration", "Status=Enabled")
                Invoke-Cmd @("aws", "s3api", "put-bucket-encryption", "--bucket", $BucketName, "--server-side-encryption-configuration", '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}')
                # DynamoDB lock table (best-effort)
                Invoke-Cmd @("aws", "dynamodb", "create-table", "--table-name", $TableName, "--attribute-definitions", "AttributeName=LockID,AttributeType=S", "--key-schema", "AttributeName=LockID,KeyType=HASH", "--billing-mode", "PAY_PER_REQUEST", "--region", $Region) 2>&1 | Out-Null
            } else {
                Write-Ok "S3 bucket $BucketName already exists."
            }

            $BackendCfg = @"
bucket         = "$BucketName"
key            = "clinigraph/$Env/terraform.tfstate"
region         = "$Region"
dynamodb_table = "$TableName"
encrypt        = true
"@
            $BackendFile = Join-Path $TfDir "backend.hcl"
            [System.IO.File]::WriteAllText($BackendFile, $BackendCfg)

            $ProvidersFile = Join-Path $TfDir "providers.tf"
            (Get-Content $ProvidersFile) -replace "# backend `"s3`" \{\}", 'backend "s3" {}' |
                Set-Content $ProvidersFile
        }
    }
}

# ── 3. Terraform init + apply ──────────────────────────────────────────────────
if (-not $SkipTerraform) {
    Write-Step "Terraform init ($Provider / $Env)"
    Push-Location $TfDir

    $BackendFile = Join-Path $TfDir "backend.hcl"
    Invoke-Cmd @("terraform", "init", "-backend-config=$BackendFile", "-reconfigure")

    Write-Step "Terraform apply ($Provider / $Env)"
    $TfVarFile = "$Env.tfvars"
    $TfVars = @("terraform", "apply", "-var-file=$TfVarFile", "-auto-approve")
    if ($Provider -eq "gcp") {
        $TfVars += "-var=project_id=$GcpProjectId"
    }
    Invoke-Cmd $TfVars

    Pop-Location
}

# ── 4. Capture Terraform outputs ──────────────────────────────────────────────
Write-Step "Reading Terraform outputs"
Push-Location $TfDir

function Get-TfOutput ([string]$name) {
    if ($DryRun) { return "DRY_RUN_PLACEHOLDER" }
    $val = terraform output -raw $name 2>$null
    if ($LASTEXITCODE -ne 0) { return "" }
    return $val
}

$RegistryUrl   = ""
$WebImageUrl   = ""
$FrontImageUrl = ""
$PostgresHost  = Get-TfOutput "postgres_host"
$PostgresPass  = Get-TfOutput "postgres_password"
$RedisHost     = Get-TfOutput "redis_host"

switch ($Provider) {
    "azure" {
        $RegistryUrl   = Get-TfOutput "acr_login_server"
        $AcrUser       = Get-TfOutput "acr_admin_username"
        $AcrPass       = Get-TfOutput "acr_admin_password"
        $WebImageUrl   = "$RegistryUrl/clinigraph-ai-web"
        $FrontImageUrl = "$RegistryUrl/clinigraph-ai-frontend"
        $AksCluster    = Get-TfOutput "aks_cluster_name"
        $ResourceGroup = Get-TfOutput "resource_group_name"
    }
    "gcp" {
        $RegistryUrl   = Get-TfOutput "registry_url"
        $WebImageUrl   = "$RegistryUrl/clinigraph-ai-web"
        $FrontImageUrl = "$RegistryUrl/clinigraph-ai-frontend"
        $GkeCluster    = Get-TfOutput "gke_cluster_name"
        $GcpRegion     = Get-TfOutput "region"
    }
    "aws" {
        $WebImageUrl   = Get-TfOutput "ecr_web_url"
        $FrontImageUrl = Get-TfOutput "ecr_frontend_url"
        $EksCluster    = Get-TfOutput "eks_cluster_name"
        $AwsRegion     = Get-TfOutput "region"
    }
}

Pop-Location
Write-Ok "Outputs captured."

# ── 5. Configure kubectl ───────────────────────────────────────────────────────
Write-Step "Configuring kubectl ($Provider)"
switch ($Provider) {
    "azure" {
        Invoke-Cmd @("az", "aks", "get-credentials", "--resource-group", $ResourceGroup, "--name", $AksCluster, "--overwrite-existing")
    }
    "gcp" {
        Invoke-Cmd @("gcloud", "container", "clusters", "get-credentials", $GkeCluster, "--region", $GcpRegion, "--project", $GcpProjectId)
    }
    "aws" {
        Invoke-Cmd @("aws", "eks", "update-kubeconfig", "--name", $EksCluster, "--region", $AwsRegion)
    }
}

# Create namespace
Invoke-Cmd @("kubectl", "create", "namespace", $Namespace, "--dry-run=client", "-o", "yaml") | Invoke-Cmd @("kubectl", "apply", "-f", "-")

Write-Ok "kubectl configured."

# ── 6. Build Docker images ─────────────────────────────────────────────────────
if (-not $SkipBuild) {
    Write-Step "Building Docker images (tag: $ImageTag)"

    # Web image
    Invoke-Cmd @("docker", "build", "-t", "$WebImageUrl`:$ImageTag", "-f", (Join-Path $RepoRoot "Dockerfile"), $RepoRoot)
    Write-Ok "Web image built: $WebImageUrl`:$ImageTag"

    # Frontend image (production multi-stage build)
    Invoke-Cmd @("docker", "build", "-t", "$FrontImageUrl`:$ImageTag", "-f", (Join-Path $InfraRoot "docker" "frontend.prod.Dockerfile"), $RepoRoot)
    Write-Ok "Frontend image built: $FrontImageUrl`:$ImageTag"

    # ── Push images ───────────────────────────────────────────────────────────
    Write-Step "Pushing images to registry"
    switch ($Provider) {
        "azure" {
            Invoke-Cmd @("az", "acr", "login", "--name", ($RegistryUrl -split "\.")[0])
        }
        "gcp" {
            Invoke-Cmd @("gcloud", "auth", "configure-docker", "$($GcpRegion)-docker.pkg.dev", "--quiet")
        }
        "aws" {
            $EcrPass = Invoke-CmdOutput @("aws", "ecr", "get-login-password", "--region", $AwsRegion)
            $EcrRegistry = $WebImageUrl -replace "/.*$", ""
            if (-not $DryRun) {
                $EcrPass | docker login --username AWS --password-stdin $EcrRegistry
            }
        }
    }

    Invoke-Cmd @("docker", "push", "$WebImageUrl`:$ImageTag")
    Invoke-Cmd @("docker", "push", "$FrontImageUrl`:$ImageTag")
    Write-Ok "Images pushed."
}

# ── 7. Generate secrets for dev (prod uses pre-set env vars) ───────────────────
Write-Step "Preparing secrets"

function New-RandomKey ([int]$Bytes = 32) {
    return [Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes($Bytes))
}

$DjangoSecretKey = if ($env:DJANGO_SECRET_KEY) { $env:DJANGO_SECRET_KEY } else { New-RandomKey 50 }
$AgentApiKey     = if ($env:AGENT_API_KEY)     { $env:AGENT_API_KEY }     else { New-RandomKey 32 }
$GrafanaPass     = if ($env:GRAFANA_ADMIN_PASSWORD) { $env:GRAFANA_ADMIN_PASSWORD } else { "admin" }

# For dev, generate a postgres password if not provided
$PgPassword = if ($env:POSTGRES_PASSWORD) { $env:POSTGRES_PASSWORD } else { New-RandomKey 24 }
# For prod with managed DB, the password comes from Terraform output
if ($Env -eq "prod" -and $PostgresPass) {
    $PgPassword = $PostgresPass
}

# ── 8. Helm deploy ─────────────────────────────────────────────────────────────
if (-not $SkipHelm) {
    Write-Step "Deploying Helm chart"

    # Install NGINX Ingress Controller if not present
    $NginxInstalled = Invoke-CmdOutput @("helm", "list", "-n", "ingress-nginx", "-q") 2>&1
    if ($NginxInstalled -notmatch "ingress-nginx") {
        Write-Ok "Installing NGINX Ingress Controller..."
        Invoke-Cmd @("helm", "repo", "add", "ingress-nginx", "https://kubernetes.github.io/ingress-nginx")
        Invoke-Cmd @("helm", "repo", "update")
        Invoke-Cmd @("helm", "upgrade", "--install", "ingress-nginx", "ingress-nginx/ingress-nginx",
            "--namespace", "ingress-nginx", "--create-namespace",
            "--set", "controller.replicaCount=1",
            "--wait", "--timeout", "5m")
    }

    # Build --set flags for dynamic values
    $HelmSetArgs = @(
        "--set", "global.imageTag=$ImageTag",
        "--set", "global.imageRegistry=",
        "--set", "web.image.repository=$WebImageUrl",
        "--set", "frontend.image.repository=$FrontImageUrl",
        "--set", "secrets.djangoSecretKey=$DjangoSecretKey",
        "--set", "secrets.agentApiKey=$AgentApiKey",
        "--set", "secrets.postgresPassword=$PgPassword",
        "--set", "secrets.grafanaAdminPassword=$GrafanaPass"
    )

    # Managed DB/Redis overrides for prod
    if ($Env -eq "prod" -and $PostgresHost) {
        $HelmSetArgs += "--set", "postgres.enabled=false"
        $HelmSetArgs += "--set", "externalDatabase.enabled=true"
        $HelmSetArgs += "--set", "externalDatabase.host=$PostgresHost"
    }
    if ($Env -eq "prod" -and $RedisHost) {
        $HelmSetArgs += "--set", "redis.enabled=false"
        $HelmSetArgs += "--set", "externalRedis.enabled=true"
        $HelmSetArgs += "--set", "externalRedis.url=redis://$RedisHost`:6379/0"
    }

    $HelmCmd = @("helm", "upgrade", "--install", $ReleaseName, $HelmDir,
        "--namespace", $Namespace, "--create-namespace",
        "-f", (Join-Path $HelmDir "values.yaml"),
        "-f", (Join-Path $HelmDir "values-$Env.yaml"),
        "-f", (Join-Path $HelmDir "values-$Provider.yaml"),
        "--wait", "--timeout", "20m"
    ) + $HelmSetArgs

    Invoke-Cmd $HelmCmd
    Write-Ok "Helm release '$ReleaseName' deployed."
}

# ── 9. Wait for web Deployment rollout ────────────────────────────────────────
Write-Step "Waiting for web Deployment to roll out"
Invoke-Cmd @("kubectl", "rollout", "status", "deployment/$ReleaseName-clinigraph-web", "-n", $Namespace, "--timeout=5m")

# ── 10. Wait for seed Job ─────────────────────────────────────────────────────
if (-not $SkipSeed) {
    Write-Step "Waiting for seed Job to complete (this may take up to 90 min on first run due to Ollama model downloads)"
    $SeedJob = "$ReleaseName-clinigraph-seed"
    Invoke-Cmd @("kubectl", "wait", "--for=condition=complete", "job/$SeedJob", "-n", $Namespace, "--timeout=7200s")
    Write-Ok "Seed Job completed."
}

# ── 11. Print access info ─────────────────────────────────────────────────────
Write-Step "Deployment complete!"

try {
    $IngressIp = Invoke-CmdOutput @("kubectl", "get", "svc", "-n", "ingress-nginx", "ingress-nginx-controller", "-o", "jsonpath='{.status.loadBalancer.ingress[0].ip}'") 2>&1
    if (-not $IngressIp -or $IngressIp -eq "''") {
        $IngressIp = Invoke-CmdOutput @("kubectl", "get", "svc", "-n", "ingress-nginx", "ingress-nginx-controller", "-o", "jsonpath='{.status.loadBalancer.ingress[0].hostname}'") 2>&1
    }
    Write-Host "`n  Ingress IP/Hostname : $IngressIp"
    Write-Host "  API               : http://$IngressIp/api/v1/"
    Write-Host "  Frontend          : http://$IngressIp/"
} catch {
    Write-Warn "Could not determine ingress address. Run: kubectl get svc -n ingress-nginx"
}

Write-Host "`n  To stream Grafana:"
Write-Host "  kubectl port-forward -n $Namespace svc/$ReleaseName-clinigraph-grafana 3000:3000"
Write-Host "`nDone! Provider=$Provider  Env=$Env  Tag=$ImageTag`n"
