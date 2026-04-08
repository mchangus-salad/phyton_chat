environment         = "prod"
location            = "eastus"
kubernetes_version  = "1.30"

system_node_vm_size = "Standard_D2s_v3"
system_node_count   = 2

# D8s_v3 = 8 vCPU / 32 GB RAM – production workloads + Ollama GPU-ready SKU
app_node_vm_size    = "Standard_D8s_v3"
app_node_min_count  = 2
app_node_max_count  = 10

acr_sku              = "Standard"

managed_postgres     = true
postgres_sku         = "GP_Standard_D2s_v3"
postgres_storage_mb  = 65536
# postgres_admin_password = set via TF_VAR_postgres_admin_password env var

managed_redis        = true
redis_sku            = "Standard"
redis_capacity       = 1
