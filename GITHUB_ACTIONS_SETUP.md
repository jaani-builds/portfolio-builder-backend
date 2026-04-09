# GitHub Actions + Terraform Deployment Guide

This setup enables fully automated infrastructure deployment: push → GitHub Actions → AWS.

## Architecture

```
Local Development
    ↓ git push
GitHub Repo
    ↓ (GitHub Actions on push to main)
Terraform Plan & Apply
    ↓
AWS Infrastructure
    ↓
Terraform State stored in S3 (locked via DynamoDB)
```

## Pre-requisites

- AWS account with credentials configured locally (temporary, for bootstrap only)
- GitHub repo with Actions enabled (should be default)
- Terraform 1.6+ installed locally (done ✅)

## Setup Steps

### 1. Bootstrap Terraform State Backend (ONE TIME ONLY)

This creates the S3 bucket and DynamoDB table that will store all future Terraform state.

```bash
cd portfolio-builder-backend/infra/terraform

# Step 1a: Temporarily disable remote backend (use local state)
# Edit backend.tf and comment it out or leave it as is initially

# Step 1b: Comment out the backend {} block in backend.tf
# (Keep state-backend.tf uncommented)

# Step 1c: Initialize Terraform with local state
terraform init

# Step 1d: Create the state backend infrastructure in AWS
terraform apply -var-file=terraform.tfvars.production
# This creates:
# - S3 bucket: portfolio-builder-terraform-state
# - DynamoDB table: terraform-locks
```

Output will show state bucket and lock table names. Copy them down.

### 2. Migrate State to S3

```bash
# Step 2a: Uncomment backend {} in backend.tf
# Now it reads:
# terraform {
#   backend "s3" {
#     bucket         = "portfolio-builder-terraform-state"
#     key            = "prod/terraform.tfstate"
#     region         = "ap-southeast-2"
#     encrypt        = true
#     dynamodb_table = "terraform-locks"
#   }
# }

# Step 2b: Run init again to migrate local state to S3
terraform init
# When prompted: "Do you want to copy existing state to the new backend?" → YES

# Verify state was migrated:
aws s3 ls s3://portfolio-builder-terraform-state/
```

### 3. Delete Bootstrap File

```bash
# Remove state-backend.tf (it was only needed to create the backend)
rm state-backend.tf

# The backend is now permanent; no need to recreate it
```

### 4. Set Up GitHub OIDC

The file `github-oidc.tf` creates an AWS OIDC provider and role for GitHub Actions.

```bash
# This is already planned in the next apply, no manual config needed
# But verify the role will be created by checking outputs:
terraform plan -var-file=terraform.tfvars.production
# Look for:
#   + aws_iam_role.github_terraform
#   + aws_iam_openid_connect_provider.github
```

### 5. Deploy OIDC and GitHub Actions Role

```bash
# Apply the OIDC changes (includes github_terraform role)
terraform apply -var-file=terraform.tfvars.production

# Copy the output:
# github_role_arn = "arn:aws:iam::<account>:role/portfolio-builder-prod-github-terraform-role"
```

### 6. Add GitHub Secret

1. Go to: https://github.com/jaani-builds/portfolio-builder-backend
2. Settings → Secrets and variables → Actions
3. Create new secret:
   - Name: `AWS_ROLE_ARN`
   - Value: (paste the github_role_arn from step 5)

### 7. Commit and Push

```bash
cd portfolio-builder-backend

git add -A
git commit -m "feat: add GitHub OIDC and Terraform remote state

- Configure S3 remote backend for Terraform state
- Add GitHub OIDC provider for OIDC-based CI/CD
- Add GitHub Actions workflow for auto-deploy on push
- No secrets stored; authentication via OIDC tokens"

git push origin main
```

### 8. Verify GitHub Actions Workflow

1. Go to: https://github.com/jaani-builds/portfolio-builder-backend/actions
2. Click the "Terraform Deploy (Production)" workflow
3. Watch the run - it should:
   - ✅ Checkout code
   - ✅ Configure AWS credentials (via OIDC)
   - ✅ Terraform init
   - ✅ Terraform plan
   - ✅ Terraform apply (auto-approved on main)

## From Here On

All future deployments are automatic:

```bash
# Make code changes
vim app/routes/auth.py

# Push to GitHub
git add app/routes/auth.py
git commit -m "fix: improve error handling"
git push origin main

# GitHub Actions automatically:
# 1. Runs Terraform plan
# 2. Applies changes to AWS
# 3. Maintains state in S3
```

## Local Development (after bootstrap)

You can now safely delete local AWS credentials since:
- GitHub Actions handles all deployments via OIDC
- You only push code

If you want to `terraform plan` locally for review before pushing:
```bash
# Still works, but optional
cd portfolio-builder-backend/infra/terraform
terraform plan -var-file=terraform.tfvars.production
# Reads state from S3 (read-only, shows what would change)
```

## Rollback / Manual Fixes

If something breaks and you need to manually apply:

```bash
# You'd need to temporarily reconfigure credentials
export AWS_PROFILE=<your-sso-profile>
cd portfolio-builder-backend/infra/terraform
terraform apply -var-file=terraform.tfvars.production
```

But this is an edge case; GitHub Actions handles 99% of deployments.

## Cleanup (after successful setup)

After step 2 is done:
```bash
# You can now remove local AWS credentials if desired
rm ~/.aws/credentials
rm ~/.aws/config

# GitHub Actions will continue to work (uses OIDC token)
# Local `terraform plan` will fail gracefully (expected - use GitHub PR workflows instead)
```

---

**Summary:** Push code → GitHub automatically deploys to AWS via OIDC. No stored secrets, no local state, no manual apply needed.
