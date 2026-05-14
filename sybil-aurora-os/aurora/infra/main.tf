terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  backend "s3" {
    bucket = "aurora-tfstate"
    key    = "sybil-aurora-os/terraform.tfstate"
    region = "us-east-1"
    encrypt = true
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region"   { default = "us-east-1" }
variable "environment"  { default = "production" }
variable "project_name" { default = "sybil-aurora-os" }

locals {
  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# ── Networking ──────────────────────────────────────────────────────────────

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "${var.project_name}-vpc"
  cidr = "10.0.0.0/16"

  azs             = ["${var.aws_region}a", "${var.aws_region}b"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24"]

  enable_nat_gateway = true
  single_nat_gateway = false

  tags = local.tags
}

# ── ECS Cluster (Sybil execution) ────────────────────────────────────────────

resource "aws_ecs_cluster" "sybil" {
  name = "${var.project_name}-sybil"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = local.tags
}

# ── Parameter Store (secrets — never hardcoded) ──────────────────────────────

resource "aws_ssm_parameter" "anthropic_api_key" {
  name  = "/${var.project_name}/anthropic_api_key"
  type  = "SecureString"
  value = "REPLACE_AT_DEPLOY_TIME"

  lifecycle {
    ignore_changes = [value]
  }

  tags = local.tags
}

# ── S3 — context store ───────────────────────────────────────────────────────

resource "aws_s3_bucket" "context_store" {
  bucket = "${var.project_name}-context-${var.environment}"
  tags   = local.tags
}

resource "aws_s3_bucket_server_side_encryption_configuration" "context_store" {
  bucket = aws_s3_bucket.context_store.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "context_store" {
  bucket = aws_s3_bucket.context_store.id
  versioning_configuration { status = "Enabled" }
}

# ── CloudWatch — observability ───────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "sybil" {
  name              = "/aws/ecs/${var.project_name}/sybil"
  retention_in_days = 30
  tags              = local.tags
}

# ── Outputs ──────────────────────────────────────────────────────────────────

output "vpc_id"           { value = module.vpc.vpc_id }
output "ecs_cluster_arn"  { value = aws_ecs_cluster.sybil.arn }
output "context_s3_bucket" { value = aws_s3_bucket.context_store.bucket }
