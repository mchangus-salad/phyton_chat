environment           = "prod"
region                = "us-east-1"
kubernetes_version    = "1.30"

# m6i.2xlarge = 8 vCPU / 32 GB
node_instance_type    = "m6i.2xlarge"
node_min_size         = 2
node_max_size         = 10
node_desired_size     = 2

managed_postgres      = true
rds_instance_class    = "db.m6g.large"
# postgres_admin_password = set via TF_VAR_postgres_admin_password

managed_redis         = true
elasticache_node_type = "cache.r6g.large"
