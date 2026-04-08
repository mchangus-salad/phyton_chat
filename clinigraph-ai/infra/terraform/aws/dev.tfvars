environment         = "dev"
region              = "us-east-1"
kubernetes_version  = "1.30"

# t3.xlarge = 4 vCPU / 16 GB – minimum for Ollama
node_instance_type  = "t3.xlarge"
node_min_size       = 1
node_max_size       = 3
node_desired_size   = 1

managed_postgres    = false
managed_redis       = false
