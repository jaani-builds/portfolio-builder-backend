terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  # LocalStack configuration for local development
  dynamic "endpoints" {
    for_each = var.use_localstack ? [1] : []
    content {
      s3             = var.localstack_endpoint
      dynamodb       = var.localstack_endpoint
      apigatewayv2   = var.localstack_endpoint
      lambda         = var.localstack_endpoint
      iam            = var.localstack_endpoint
      sts            = var.localstack_endpoint
      logs           = var.localstack_endpoint
      cloudwatch     = var.localstack_endpoint
      sns            = var.localstack_endpoint
      acm            = var.localstack_endpoint
    }
  }

  # LocalStack doesn't validate credentials, so we can use dummy values
  dynamic "skip_credentials_validation" {
    for_each = var.use_localstack ? [1] : []
    content {
      skip_credentials_validation = true
      skip_requesting_account_id  = true
    }
  }
}
