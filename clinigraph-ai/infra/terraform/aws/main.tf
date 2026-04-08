data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  prefix = "${var.project}-${var.environment}"
  azs    = slice(data.aws_availability_zones.available.names, 0, 2)
}

# ── VPC ───────────────────────────────────────────────────────────────────────
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags                 = { Name = "vpc-${local.prefix}" }
}

resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.${count.index}.0/24"
  availability_zone = local.azs[count.index]
  tags = {
    Name                                        = "snet-private-${local.prefix}-${count.index}"
    "kubernetes.io/cluster/eks-${local.prefix}" = "owned"
    "kubernetes.io/role/internal-elb"           = "1"
  }
}

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.${count.index + 100}.0/24"
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = true
  tags = {
    Name                                        = "snet-public-${local.prefix}-${count.index}"
    "kubernetes.io/cluster/eks-${local.prefix}" = "owned"
    "kubernetes.io/role/elb"                    = "1"
  }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "igw-${local.prefix}" }
}

resource "aws_eip" "nat" {
  domain = "vpc"
  tags   = { Name = "eip-nat-${local.prefix}" }
}

resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id
  tags          = { Name = "nat-${local.prefix}" }
  depends_on    = [aws_internet_gateway.main]
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
  tags = { Name = "rt-public-${local.prefix}" }
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main.id
  }
  tags = { Name = "rt-private-${local.prefix}" }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private" {
  count          = 2
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# ── ECR Repositories ─────────────────────────────────────────────────────────
resource "aws_ecr_repository" "web" {
  name                 = "${local.prefix}-web"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecr_repository" "frontend" {
  name                 = "${local.prefix}-frontend"
  image_tag_mutability = "MUTABLE"
}

# ── IAM for EKS cluster ───────────────────────────────────────────────────────
resource "aws_iam_role" "eks_cluster" {
  name = "role-eks-${local.prefix}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "eks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "eks_cluster_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
  role       = aws_iam_role.eks_cluster.name
}

# ── IAM for EKS nodes ─────────────────────────────────────────────────────────
resource "aws_iam_role" "eks_nodes" {
  name = "role-eks-nodes-${local.prefix}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "eks_node_policies" {
  for_each = toset([
    "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",
    "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy",
    "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
  ])
  policy_arn = each.key
  role       = aws_iam_role.eks_nodes.name
}

# ── EKS Cluster ───────────────────────────────────────────────────────────────
resource "aws_eks_cluster" "main" {
  name     = "eks-${local.prefix}"
  role_arn = aws_iam_role.eks_cluster.arn
  version  = var.kubernetes_version

  vpc_config {
    subnet_ids              = concat(aws_subnet.private[*].id, aws_subnet.public[*].id)
    endpoint_private_access = true
    endpoint_public_access  = true
  }

  depends_on = [aws_iam_role_policy_attachment.eks_cluster_policy]
}

resource "aws_eks_node_group" "app" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "app"
  node_role_arn   = aws_iam_role.eks_nodes.arn
  subnet_ids      = aws_subnet.private[*].id
  instance_types  = [var.node_instance_type]

  scaling_config {
    desired_size = var.node_desired_size
    min_size     = var.node_min_size
    max_size     = var.node_max_size
  }

  disk_size  = 200
  depends_on = [aws_iam_role_policy_attachment.eks_node_policies]
}

# ── RDS PostgreSQL (prod only) ────────────────────────────────────────────────
resource "aws_db_subnet_group" "main" {
  count      = var.managed_postgres ? 1 : 0
  name       = "dbsng-${local.prefix}"
  subnet_ids = aws_subnet.private[*].id
}

resource "random_password" "postgres" {
  count   = var.managed_postgres ? 1 : 0
  length  = 24
  special = false
}

resource "aws_db_instance" "postgres" {
  count                  = var.managed_postgres ? 1 : 0
  identifier             = "rds-${local.prefix}"
  engine                 = "postgres"
  engine_version         = "16"
  instance_class         = var.rds_instance_class
  allocated_storage      = 20
  max_allocated_storage  = 200
  db_name                = "clinigraph"
  username               = "clinigraph"
  password               = coalesce(var.postgres_admin_password, random_password.postgres[0].result)
  db_subnet_group_name   = aws_db_subnet_group.main[0].name
  skip_final_snapshot    = var.environment != "prod"
  deletion_protection    = var.environment == "prod"
  multi_az               = var.environment == "prod"
  storage_encrypted      = true
}

# ── ElastiCache Redis (prod only) ─────────────────────────────────────────────
resource "aws_elasticache_subnet_group" "main" {
  count      = var.managed_redis ? 1 : 0
  name       = "ecsg-${local.prefix}"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_elasticache_cluster" "redis" {
  count                = var.managed_redis ? 1 : 0
  cluster_id           = "ec-${local.prefix}"
  engine               = "redis"
  node_type            = var.elasticache_node_type
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  engine_version       = "7.0"
  port                 = 6379
  subnet_group_name    = aws_elasticache_subnet_group.main[0].name
}
