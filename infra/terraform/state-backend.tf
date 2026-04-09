# This file creates the S3 bucket and DynamoDB table for Terraform state
# Run this ONCE manually, then remove it after the backend is created
# Uncomment the backend {} block in backend.tf after this succeeds

# NOTE: Only needed for initial bootstrap. After deployment, this can be removed.
# To bootstrap the backend:
# 1. Comment out backend {} in backend.tf
# 2. Run: terraform init (this will use local state)
# 3. Run: terraform apply (creates bucket and lock table)
# 4. Uncomment backend {} in backend.tf
# 5. Run: terraform init (migrates state to S3)
# 6. Delete this file and push to GitHub
# 7. GitHub Actions will maintain state in S3 going forward

resource "aws_s3_bucket" "terraform_state" {
  bucket = "portfolio-builder-terraform-state"
}

resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_dynamodb_table" "terraform_locks" {
  name           = "terraform-locks"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }
}

output "state_bucket_name" {
  description = "S3 bucket for storing Terraform state"
  value       = aws_s3_bucket.terraform_state.bucket
}

output "state_lock_table_name" {
  description = "DynamoDB table for Terraform state locks"
  value       = aws_dynamodb_table.terraform_locks.name
}
