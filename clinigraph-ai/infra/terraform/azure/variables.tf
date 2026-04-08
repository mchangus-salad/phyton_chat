variable "project" {
  description = "Short project name, used as prefix in all resource names"
  type        = string
  default     = "clinigraph"
}

variable "environment" {
  description = "Deployment environment: dev or prod"
  type        = string
  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be 'dev' or 'prod'."
  }
}

variable "location" {
  description = "Azure region for all resources"
  type        = string
  default     = "eastus"
}

variable "kubernetes_version" {
  description = "AKS Kubernetes version"
  type        = string
  default     = "1.30"
}

# ── System node pool ──────────────────────────────────────────────────────────
variable "system_node_vm_size" {
  type    = string
  default = "Standard_D2s_v3"
}

variable "system_node_count" {
  type    = number
  default = 1
}

# ── App node pool (runs web, weaviate, ollama, etc.) ─────────────────────────
variable "app_node_vm_size" {
  description = "VM size – must have ≥16 GB RAM to host Ollama (llama3.1:8b needs ~8 GB)"
  type        = string
  default     = "Standard_D4s_v3"
}

variable "app_node_min_count" {
  type    = number
  default = 1
}

variable "app_node_max_count" {
  type    = number
  default = 5
}

# ── Container Registry ────────────────────────────────────────────────────────
variable "acr_sku" {
  type    = string
  default = "Basic"
}

# ── Managed PostgreSQL (prod only) ────────────────────────────────────────────
variable "managed_postgres" {
  description = "If true, provision Azure Database for PostgreSQL Flexible Server (recommended for prod)"
  type        = bool
  default     = false
}

variable "postgres_sku" {
  type    = string
  default = "B_Standard_B1ms"
}

variable "postgres_storage_mb" {
  type    = number
  default = 32768
}

variable "postgres_admin_password" {
  type      = string
  sensitive = true
  default   = ""
}

# ── Managed Redis (prod only) ─────────────────────────────────────────────────
variable "managed_redis" {
  description = "If true, provision Azure Cache for Redis (recommended for prod)"
  type        = bool
  default     = false
}

variable "redis_sku" {
  type    = string
  default = "Basic"
}

variable "redis_capacity" {
  description = "Redis cache size in GB (0 = C0 250 MB)"
  type        = number
  default     = 0
}
