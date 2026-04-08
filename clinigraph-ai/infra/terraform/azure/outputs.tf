output "resource_group_name" {
  description = "Name of the Azure Resource Group"
  value       = azurerm_resource_group.main.name
}

output "aks_cluster_name" {
  description = "Name of the AKS cluster"
  value       = azurerm_kubernetes_cluster.main.name
}

output "acr_login_server" {
  description = "ACR login server (e.g. myregistry.azurecr.io)"
  value       = azurerm_container_registry.acr.login_server
}

output "acr_admin_username" {
  sensitive = true
  value     = azurerm_container_registry.acr.admin_username
}

output "acr_admin_password" {
  sensitive = true
  value     = azurerm_container_registry.acr.admin_password
}

output "kubeconfig" {
  description = "Raw kubeconfig for the AKS cluster"
  sensitive   = true
  value       = azurerm_kubernetes_cluster.main.kube_config_raw
}

output "postgres_host" {
  description = "FQDN of the managed PostgreSQL server (empty if managed_postgres=false)"
  value       = var.managed_postgres ? azurerm_postgresql_flexible_server.main[0].fqdn : ""
}

output "postgres_password" {
  sensitive = true
  value = var.managed_postgres ? coalesce(
    var.postgres_admin_password,
    random_password.postgres[0].result,
  ) : ""
}

output "redis_host" {
  description = "Hostname of the managed Redis cache (empty if managed_redis=false)"
  value       = var.managed_redis ? azurerm_redis_cache.main[0].hostname : ""
}

output "redis_primary_key" {
  sensitive = true
  value     = var.managed_redis ? azurerm_redis_cache.main[0].primary_access_key : ""
}
