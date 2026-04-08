output "eks_cluster_name" {
  value = aws_eks_cluster.main.name
}

output "ecr_web_url" {
  description = "ECR URL for the web (Django) image"
  value       = aws_ecr_repository.web.repository_url
}

output "ecr_frontend_url" {
  description = "ECR URL for the frontend image"
  value       = aws_ecr_repository.frontend.repository_url
}

output "region" {
  value = var.region
}

output "postgres_host" {
  value = var.managed_postgres ? aws_db_instance.postgres[0].address : ""
}

output "postgres_password" {
  sensitive = true
  value     = var.managed_postgres ? coalesce(var.postgres_admin_password, random_password.postgres[0].result) : ""
}

output "redis_host" {
  value = var.managed_redis ? aws_elasticache_cluster.redis[0].cache_nodes[0].address : ""
}
