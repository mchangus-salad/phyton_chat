environment       = "dev"
region            = "us-central1"
zone              = "us-central1-a"

# n2-standard-4 = 4 vCPU / 16 GB – minimum for Ollama
node_machine_type = "n2-standard-4"
node_min_count    = 1
node_max_count    = 3

managed_postgres  = false
managed_redis     = false

# project_id must be set via TF_VAR_project_id or -var="project_id=<your-project>"
