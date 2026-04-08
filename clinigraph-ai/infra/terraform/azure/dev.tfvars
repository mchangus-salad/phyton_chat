environment         = "dev"
location            = "eastus"
kubernetes_version  = "1.30"

system_node_vm_size = "Standard_D2s_v3"
system_node_count   = 1

# D4s_v3 = 4 vCPU / 16 GB RAM – enough for Ollama llama3.1:8b
app_node_vm_size    = "Standard_D4s_v3"
app_node_min_count  = 1
app_node_max_count  = 3

acr_sku             = "Basic"
managed_postgres    = false
managed_redis       = false
