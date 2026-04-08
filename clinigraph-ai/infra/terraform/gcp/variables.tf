variable "project_id" {
  description = "GCP Project ID (required – set via TF_VAR_project_id or --var)"
  type        = string
}

variable "project" {
  description = "Short project name for resource labeling"
  type        = string
  default     = "clinigraph"
}

variable "environment" {
  type = string
  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "Must be 'dev' or 'prod'."
  }
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "zone" {
  type    = string
  default = "us-central1-a"
}

# ── GKE ───────────────────────────────────────────────────────────────────────
variable "node_machine_type" {
  description = "n2-standard-4 = 4 vCPU / 16 GB – minimum for Ollama"
  type        = string
  default     = "n2-standard-4"
}

variable "node_min_count" {
  type    = number
  default = 1
}

variable "node_max_count" {
  type    = number
  default = 5
}

# ── Cloud SQL (prod only) ─────────────────────────────────────────────────────
variable "managed_postgres" {
  type    = bool
  default = false
}

variable "postgres_tier" {
  type    = string
  default = "db-f1-micro"
}

variable "postgres_admin_password" {
  type      = string
  sensitive = true
  default   = ""
}

# ── Cloud Memorystore Redis (prod only) ───────────────────────────────────────
variable "managed_redis" {
  type    = bool
  default = false
}

variable "redis_tier" {
  description = "BASIC or STANDARD_HA"
  type        = string
  default     = "BASIC"
}

variable "redis_memory_size_gb" {
  type    = number
  default = 1
}
