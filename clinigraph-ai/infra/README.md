# CliniGraph AI – Infrastructure & Deployment Guide

## Overview

A **single PowerShell script** provisions cloud infrastructure and deploys the full CliniGraph AI stack to any of the three supported cloud providers:

| Cloud | Kubernetes | Registry |
|---|---|---|
| Azure | AKS | Azure Container Registry (ACR) |
| GCP | GKE | Google Artifact Registry |
| AWS | EKS | Amazon ECR |

---

## Prerequisites

Install the following tools and ensure they are on your `PATH`:

| Tool | Min version | Install |
|---|---|---|
| Terraform | 1.7+ | https://terraform.io/downloads |
| Helm | 3.14+ | https://helm.sh/docs/intro/install |
| kubectl | 1.30+ | https://kubernetes.io/docs/tasks/tools |
| Docker Desktop | 24+ | https://docs.docker.com/desktop |
| Azure CLI | 2.60+ | `winget install Microsoft.AzureCLI` |
| gcloud CLI | latest | https://cloud.google.com/sdk/docs/install |
| AWS CLI | 2.x | https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html |

You only need the provider-specific CLI for the target cloud.

---

## Quick Start

```powershell
cd clinigraph-ai/infra

# Azure – dev environment
.\deploy.ps1 -Provider azure -Env dev

# GCP – dev environment
.\deploy.ps1 -Provider gcp -Env dev -GcpProjectId my-gcp-project

# AWS – dev environment
.\deploy.ps1 -Provider aws -Env dev

# Any provider – production
.\deploy.ps1 -Provider azure -Env prod -ImageTag v1.2.3
```

> **First run:** Ollama model downloads (`llama3.1:8b` ≈ 5 GB) happen during the seed Job.  
> Expect 15–90 minutes depending on node bandwidth. Monitor with:
> ```powershell
> kubectl logs -n clinigraph -f job/clinigraph-clinigraph-seed
> ```

---

## Script Parameters

| Parameter | Required | Description |
|---|---|---|
| `-Provider` | ✅ | `azure` / `gcp` / `aws` |
| `-Env` | ✅ | `dev` / `prod` |
| `-ImageTag` | – | Docker tag to build and deploy (default: `latest`) |
| `-Namespace` | – | Kubernetes namespace (default: `clinigraph`) |
| `-ReleaseName` | – | Helm release name (default: `clinigraph`) |
| `-GcpProjectId` | GCP only | GCP project ID (or set `$env:GCP_PROJECT_ID`) |
| `-SkipTerraform` | – | Assume infra already exists |
| `-SkipBuild` | – | Assume images already pushed to registry |
| `-SkipHelm` | – | Skip Helm deployment |
| `-SkipSeed` | – | Don't wait for seed Job |
| `-DryRun` | – | Print commands without executing |

---

## What the Script Does

```
1. Validate prerequisites (terraform, helm, kubectl, docker, cloud CLI)
2. Bootstrap remote Terraform state storage (Azure Blob / GCS / S3)
3. terraform init  (using generated backend.hcl)
4. terraform apply -var-file=<env>.tfvars
5. Read outputs (registry URL, cluster name, DB/Redis endpoints)
6. Configure kubectl  (az aks get-credentials / gcloud get-credentials / aws eks update-kubeconfig)
7. docker build  web image  (from repo Dockerfile)
8. docker build  frontend image  (from infra/docker/frontend.prod.Dockerfile)
9. docker push   both images to cloud registry
10. helm upgrade --install  (merges values.yaml + values-<env>.yaml + values-<provider>.yaml)
11. kubectl rollout status  (wait for web Deployment)
12. kubectl wait  job/…-seed  (wait up to 2 h for migrations + corpus import)
13. Print access URLs
```

---

## Environment Variables (Secrets)

For **dev**, the script auto-generates random values for:
- `DJANGO_SECRET_KEY`
- `AGENT_API_KEY`
- `POSTGRES_PASSWORD`

For **prod**, set these environment variables before running:

```powershell
$env:DJANGO_SECRET_KEY     = "your-50-char-secret"
$env:AGENT_API_KEY         = "your-api-key"
$env:POSTGRES_PASSWORD     = "your-db-password"   # or let Terraform generate it
$env:GRAFANA_ADMIN_PASSWORD = "your-grafana-pass"
```

---

## Infrastructure Layout

### Dev Environment
All services run **in-cluster** (Kubernetes pods):

```
postgres  → StatefulSet (10 Gi PVC)
redis     → StatefulSet (2 Gi PVC)
kafka     → StatefulSet (10 Gi PVC)
weaviate  → StatefulSet (20 Gi PVC)
ollama    → StatefulSet (60 Gi PVC)
prometheus, grafana  → Deployments
web, frontend        → Deployments
```

### Prod Environment
Postgres and Redis use **managed cloud services**:

| Service | Azure | GCP | AWS |
|---|---|---|---|
| PostgreSQL | Azure Database for PostgreSQL Flexible Server | Cloud SQL | RDS PostgreSQL |
| Redis | Azure Cache for Redis | Cloud Memorystore | ElastiCache |
| Kubernetes | AKS | GKE | EKS |
| Registry | ACR | Artifact Registry | ECR |

---

## Helm Chart

Located at `infra/helm/clinigraph/`.

### Values merge order (last wins):
```
values.yaml  →  values-dev.yaml OR values-prod.yaml  →  values-<provider>.yaml  →  --set flags
```

### Key toggles:

```yaml
postgres.enabled: true       # false in prod (use managed DB)
redis.enabled: true          # false in prod (use managed cache)
externalDatabase.enabled: false  # true in prod
externalRedis.enabled: false     # true in prod
ollama.models:               # models pulled during first seed run
  - llama3.1:8b
  - nomic-embed-text
seed.pullOllamaModels: true  # set false in prod after first deploy
```

### Manual Helm deploy (without deploy.ps1):

```powershell
helm upgrade --install clinigraph ./infra/helm/clinigraph \
  --namespace clinigraph --create-namespace \
  -f infra/helm/clinigraph/values.yaml \
  -f infra/helm/clinigraph/values-dev.yaml \
  -f infra/helm/clinigraph/values-azure.yaml \
  --set global.imageRegistry=myacr.azurecr.io \
  --set secrets.djangoSecretKey=changeme \
  --set secrets.agentApiKey=changeme \
  --set secrets.postgresPassword=changeme
```

---

## Terraform

### Azure (`infra/terraform/azure/`)

```powershell
cd infra/terraform/azure
terraform init -backend-config=backend.hcl
terraform apply -var-file=dev.tfvars
```

Key resources: **Resource Group, VNet, AKS cluster + app node pool, ACR, Log Analytics**.  
Prod adds: **Azure Database for PostgreSQL Flexible Server, Azure Cache for Redis**.

### GCP (`infra/terraform/gcp/`)

```powershell
cd infra/terraform/gcp
terraform init -backend-config=backend.hcl
terraform apply -var-file=dev.tfvars -var="project_id=YOUR_PROJECT"
```

Key resources: **VPC + GKE subnet (pod/svc secondary ranges), Artifact Registry, GKE cluster + node pool**.  
Prod adds: **Cloud SQL (PostgreSQL 16), Cloud Memorystore Redis**.

### AWS (`infra/terraform/aws/`)

```powershell
cd infra/terraform/aws
terraform init -backend-config=backend.hcl
terraform apply -var-file=dev.tfvars
```

Key resources: **VPC (2 AZ), IGW + NAT, ECR ×2, EKS cluster + managed node group**.  
Prod adds: **RDS PostgreSQL 16, ElastiCache Redis**.

---

## Folder Structure

```
infra/
├── terraform/
│   ├── azure/           # AKS + ACR + optional managed DB/Redis
│   │   ├── providers.tf
│   │   ├── variables.tf
│   │   ├── main.tf
│   │   ├── outputs.tf
│   │   ├── dev.tfvars
│   │   └── prod.tfvars
│   ├── gcp/             # GKE + Artifact Registry + optional Cloud SQL/Memorystore
│   └── aws/             # EKS + ECR + optional RDS/ElastiCache
├── helm/clinigraph/
│   ├── Chart.yaml
│   ├── values.yaml          # Base defaults
│   ├── values-dev.yaml      # Dev overrides (all in-cluster)
│   ├── values-prod.yaml     # Prod overrides (managed DB/Redis, HA)
│   ├── values-azure.yaml    # Azure StorageClass + ingress annotations
│   ├── values-gcp.yaml      # GCP StorageClass
│   ├── values-aws.yaml      # AWS StorageClass
│   └── templates/           # K8s manifests (26 files)
├── docker/
│   ├── frontend.prod.Dockerfile   # Multi-stage React → Nginx
│   └── frontend.nginx.conf        # SPA routing + cache headers
├── deploy.ps1           # Main deployment entry point
└── README.md            # This file
```

---

## Troubleshooting

### Seed Job is stuck / timed out
```powershell
kubectl describe job/clinigraph-clinigraph-seed -n clinigraph
kubectl logs -n clinigraph -l app.kubernetes.io/component=seed
```

### Ollama model pull fails
Pull models manually:
```powershell
kubectl exec -n clinigraph sts/clinigraph-clinigraph-ollama -- ollama pull llama3.1:8b
kubectl exec -n clinigraph sts/clinigraph-clinigraph-ollama -- ollama pull nomic-embed-text
```

### Weaviate collection missing after redeploy
The Weaviate PVC persists data across redeployments. If it was deleted:
```powershell
# Re-run the seed job
kubectl delete job/clinigraph-clinigraph-seed -n clinigraph
helm upgrade clinigraph ./infra/helm/clinigraph -n clinigraph --reuse-values
```

### Force secret rotation
```powershell
.\deploy.ps1 -Provider azure -Env dev -SkipTerraform -SkipBuild
```

---

## Cost Estimates (approximate on-demand pricing)

| Environment | Azure | GCP | AWS |
|---|---|---|---|
| Dev (1 × D4s_v3) | ~$140/mo | ~$130/mo | ~$120/mo |
| Prod (2–10 × D8s_v3 + managed DB/Redis) | ~$700–2 500/mo | ~$650–2 300/mo | ~$600–2 200/mo |

> Shut down dev clusters when not needed:  
> `az aks stop --name aks-clinigraph-dev --resource-group rg-clinigraph-dev`
