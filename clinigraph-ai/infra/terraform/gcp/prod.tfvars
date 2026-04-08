environment       = "prod"
region            = "us-central1"
zone              = "us-central1-a"

# n2-standard-8 = 8 vCPU / 32 GB
node_machine_type = "n2-standard-8"
node_min_count    = 2
node_max_count    = 10

managed_postgres     = true
postgres_tier        = "db-custom-2-7680"
# postgres_admin_password = set via TF_VAR_postgres_admin_password

managed_redis        = true
redis_tier           = "STANDARD_HA"
redis_memory_size_gb = 4

# project_id must be set via TF_VAR_project_id or -var="project_id=<your-project>"
