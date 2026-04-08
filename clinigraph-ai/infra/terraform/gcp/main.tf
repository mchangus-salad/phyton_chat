locals {
  prefix = "${var.project}-${var.environment}"
  labels = {
    project     = var.project
    environment = var.environment
    managed_by  = "terraform"
  }
}

# ── Enable required APIs ───────────────────────────────────────────────────────
resource "google_project_service" "services" {
  for_each = toset([
    "container.googleapis.com",
    "artifactregistry.googleapis.com",
    "sqladmin.googleapis.com",
    "redis.googleapis.com",
    "compute.googleapis.com",
    "servicenetworking.googleapis.com",
  ])
  service            = each.key
  disable_on_destroy = false
}

# ── VPC ───────────────────────────────────────────────────────────────────────
resource "google_compute_network" "main" {
  name                    = "vpc-${local.prefix}"
  auto_create_subnetworks = false
  depends_on              = [google_project_service.services]
}

resource "google_compute_subnetwork" "gke" {
  name          = "snet-gke-${local.prefix}"
  ip_cidr_range = "10.0.0.0/20"
  region        = var.region
  network       = google_compute_network.main.id

  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = "10.48.0.0/14"
  }
  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = "10.52.0.0/20"
  }
}

# ── Artifact Registry ─────────────────────────────────────────────────────────
resource "google_artifact_registry_repository" "main" {
  location      = var.region
  repository_id = local.prefix
  format        = "DOCKER"
  labels        = local.labels
  depends_on    = [google_project_service.services]
}

# ── GKE Service Account ───────────────────────────────────────────────────────
resource "google_service_account" "gke_nodes" {
  account_id   = "sa-gke-${var.environment}"
  display_name = "GKE Node SA (${var.environment})"
}

resource "google_project_iam_member" "gke_artifact_reader" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

resource "google_project_iam_member" "gke_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

# ── GKE Cluster ───────────────────────────────────────────────────────────────
resource "google_container_cluster" "main" {
  name     = "gke-${local.prefix}"
  location = var.region

  network    = google_compute_network.main.id
  subnetwork = google_compute_subnetwork.gke.id

  remove_default_node_pool = true
  initial_node_count       = 1

  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  depends_on = [google_project_service.services]

  lifecycle {
    ignore_changes = [initial_node_count]
  }
}

resource "google_container_node_pool" "app" {
  name     = "app"
  cluster  = google_container_cluster.main.id
  location = var.region

  autoscaling {
    min_node_count = var.node_min_count
    max_node_count = var.node_max_count
  }

  node_config {
    machine_type    = var.node_machine_type
    disk_size_gb    = 200
    service_account = google_service_account.gke_nodes.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]
    labels          = local.labels
    metadata = {
      disable-legacy-endpoints = "true"
    }
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }
}

# ── Cloud SQL for PostgreSQL (prod only) ─────────────────────────────────────
resource "random_password" "postgres" {
  count   = var.managed_postgres ? 1 : 0
  length  = 24
  special = false
}

resource "google_sql_database_instance" "main" {
  count            = var.managed_postgres ? 1 : 0
  name             = "psql-${local.prefix}"
  database_version = "POSTGRES_16"
  region           = var.region

  settings {
    tier = var.postgres_tier
    ip_configuration {
      ipv4_enabled = true
      authorized_networks {
        name  = "allow-all-temp"
        value = "0.0.0.0/0"
      }
    }
    backup_configuration {
      enabled = var.environment == "prod"
    }
  }

  deletion_protection = var.environment == "prod"
  depends_on          = [google_project_service.services]
}

resource "google_sql_database" "clinigraph" {
  count    = var.managed_postgres ? 1 : 0
  name     = "clinigraph"
  instance = google_sql_database_instance.main[0].name
}

resource "google_sql_user" "clinigraph" {
  count    = var.managed_postgres ? 1 : 0
  name     = "clinigraph"
  instance = google_sql_database_instance.main[0].name
  password = coalesce(var.postgres_admin_password, random_password.postgres[0].result)
}

# ── Cloud Memorystore Redis (prod only) ───────────────────────────────────────
resource "google_redis_instance" "main" {
  count          = var.managed_redis ? 1 : 0
  name           = "redis-${local.prefix}"
  tier           = var.redis_tier
  memory_size_gb = var.redis_memory_size_gb
  region         = var.region
  authorized_network = google_compute_network.main.id
  labels         = local.labels
  depends_on     = [google_project_service.services]
}
