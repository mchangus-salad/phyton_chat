variable "project" {
  type    = string
  default = "clinigraph"
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
  default = "us-east-1"
}

# ── EKS ───────────────────────────────────────────────────────────────────────
variable "kubernetes_version" {
  type    = string
  default = "1.30"
}

variable "node_instance_type" {
  description = "t3.xlarge = 4 vCPU / 16 GB – minimum for Ollama"
  type        = string
  default     = "t3.xlarge"
}

variable "node_min_size" {
  type    = number
  default = 1
}

variable "node_max_size" {
  type    = number
  default = 5
}

variable "node_desired_size" {
  type    = number
  default = 1
}

# ── RDS PostgreSQL (prod only) ────────────────────────────────────────────────
variable "managed_postgres" {
  type    = bool
  default = false
}

variable "rds_instance_class" {
  type    = string
  default = "db.t3.micro"
}

variable "postgres_admin_password" {
  type      = string
  sensitive = true
  default   = ""
}

# ── ElastiCache Redis (prod only) ─────────────────────────────────────────────
variable "managed_redis" {
  type    = bool
  default = false
}

variable "elasticache_node_type" {
  type    = string
  default = "cache.t3.micro"
}
