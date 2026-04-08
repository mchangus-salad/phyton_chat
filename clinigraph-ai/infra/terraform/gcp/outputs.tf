output "gke_cluster_name" {
  value = google_container_cluster.main.name
}

output "registry_url" {
  description = "Artifact Registry URL prefix for tagging images"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${local.prefix}"
}

output "postgres_host" {
  value = var.managed_postgres ? google_sql_database_instance.main[0].public_ip_address : ""
}

output "postgres_password" {
  sensitive = true
  value     = var.managed_postgres ? coalesce(var.postgres_admin_password, random_password.postgres[0].result) : ""
}

output "redis_host" {
  value = var.managed_redis ? google_redis_instance.main[0].host : ""
}

output "region" {
  value = var.region
}

output "project_id" {
  value = var.project_id
}
