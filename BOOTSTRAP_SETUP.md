# Terraform Bootstrap Setup Guide

## Overview
The bootstrap workflow (`bootstrap-terraform.yml`) is a **one-time setup** that provisions the foundational AWS infrastructure needed for deploying the portfolio-builder application. It creates:

1. **S3 bucket** for Terraform state storage
2. **DynamoDB table** for state locking
3. **Lambda function** and related infrastructure
4. **GitHub OIDC provider** for secure, passwordless deployments

---

## Prerequisites

### 1. AWS Account Setup
- **AWS Account ID**: `353695642481` (currently hardcoded - update if different)
- **IAM Permissions**: User needs permissions to create S3, DynamoDB, Lambda, IAM roles, API Gateway, and CloudWatch resources
- **Temporary AWS Credentials**: Store these as GitHub secrets (for bootstrap only - will be replaced with OIDC later)

### 2. GitHub Secrets Configuration
Set these secrets in your GitHub repository (Settings → Secrets and variables → Actions):

| Secret Name | Value | Notes |
|---|---|---|
| `AWS_ACCESS_KEY_ID` | Your AWS access key | Temporary - for bootstrap only |
| `AWS_SECRET_ACCESS_KEY` | Your AWS secret key | Temporary - for bootstrap only |
| `OAUTH_CLIENT_ID` | GitHub OAuth app client ID | From: https://github.com/settings/developers → OAuth Apps |
| `OAUTH_CLIENT_SECRET` | GitHub OAuth app client secret | ⚠️ **SENSITIVE** - never commit |
| `JWT_SECRET` | Random 64+ character string | Generate: `openssl rand -base64 64` |

### 3. GitHub OAuth App
Create a GitHub OAuth app at https://github.com/settings/developers/new:
- **Authorization callback URL**: Will be set after bootstrap completes (use `http://localhost:3000/auth/github/callback` for local testing)
- Store the Client ID and Client Secret in GitHub Actions secrets

### 4. GitHub Variables (Optional)
Set these variables for customization (Settings → Secrets and variables → Actions):

| Variable Name | Default | Purpose |
|---|---|---|
| `FRONTEND_URL` | `https://portfolio-builder-frontend.jaanifrancis.workers.dev` | OAuth redirect URL |
| `ALERT_EMAIL` | `jaaninickolas@icloud.com` | CloudWatch alarm notifications |

---

## Why Bootstrap Failed

### Root Causes

#### 1. Missing GitHub Secrets ⚠️ **Most Likely**
If `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`, or `JWT_SECRET` secrets are not set, Terraform receives empty values and planning fails with:
```
Error: Required variable missing - "github_client_id", "github_client_secret", "jwt_secret" cannot be empty
```

**Fix**: Set all required secrets in GitHub Actions settings.

#### 2. Hardcoded Secrets in terraform.tfvars.production ✅ **FIXED**
The production Terraform vars file was committing sensitive values to version control. These are now removed because:
- GitHub Actions workflow passes them as `TF_VAR_*` environment variables
- Version control should never contain secrets
- The `.gitignore` already marks this file as ignored

**Status**: Fixed - secrets removed from [terraform.tfvars.production](infra/terraform/terraform.tfvars.production)

#### 3. AWS Account Mismatch
The workflow hardcodes account ID `353695642481`. If your AWS credentials belong to a different account, bootstrap fails immediately:
```
ERROR: Wrong AWS account! Expected 353695642481, got 123456789012
```

**Fix**: Either:
- Update `.github/workflows/bootstrap-terraform.yml` with your actual AWS account ID
- Update [infra/terraform/backend.tf](infra/terraform/backend.tf) with your account-specific bucket name

---

## Running Bootstrap

### Step 1: Set GitHub Secrets
```bash
# Go to GitHub repo → Settings → Secrets and variables → Actions
# Add the required secrets listed above
```

### Step 2: Trigger Workflow
1. Go to Actions tab in GitHub
2. Select "Terraform Bootstrap (ONE-TIME SETUP)"
3. Click "Run workflow" button
4. Monitor logs in the "bootstrap" job

### Step 3: Verify Success
Successful bootstrap shows:
```
✅ Bootstrap Complete!

Next steps:
1. Add GitHub secret: AWS_ROLE_ARN = <output_value>
2. Delete AWS credential secrets
3. Delete .github/workflows/bootstrap-terraform.yml
4. Push changes to trigger permanent OIDC deployment
```

### Step 4: Transition to OIDC
After bootstrap succeeds:
1. Copy the GitHub OIDC Role ARN from the workflow output
2. Add `AWS_ROLE_ARN` as a GitHub secret with the output value
3. Delete the temporary `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` secrets
4. Delete the `bootstrap-terraform.yml` workflow file
5. Push to trigger `terraform-deploy.yml` (which uses OIDC authentication)

---

## Handling Multi-Run Bootstrap (Resources Already Exist)

If bootstrap has been run before, you may see errors like:
```
Error: creating IAM OIDC Provider: EntityAlreadyExists: 
  Provider with url https://token.actions.githubusercontent.com already exists.

Error: creating IAM Role: EntityAlreadyExists: 
  Role with name portfolio-builder-prod-lambda-role already exists.

Error: creating Budget: DuplicateRecordException: 
  the budget already exists.
```

This is **normal** on subsequent bootstrap runs. The resources already exist in AWS but not in your Terraform state.

### Recovery Steps

1. **Apply the Terraform fixes** (already done):
   - ✅ Updated backend.tf to use `use_lockfile` instead of deprecated `dynamodb_table`
   - ✅ Made GitHub OIDC provider conditional to handle existing resources
   - ✅ Made Lambda role handle creation conflicts
   - ✅ Made AWS Budget conditional on `create_billing_alarm` flag

2. **Run the recovery script** to import existing resources:
   ```bash
   cd portfolio-builder-backend
   bash RECOVER_BOOTSTRAP.sh
   ```

3. **Verify the state** matches AWS:
   ```bash
   cd infra/terraform
   terraform plan
   ```
   You should see:
   ```
   No changes. Infrastructure is up-to-date.
   ```

4. **Delete existing resources** (if you need to restart from scratch):
   ```bash
   # Lists all existing AWS resources for portfolio-builder
   aws s3 ls | grep portfolio-builder
   aws iam list-roles --query "Roles[?contains(RoleName, 'portfolio-builder')]"
   aws iam list-open-id-connect-providers
   aws budgets describe-budgets --account-id <YOUR_ACCOUNT_ID>
   
   # Then delete them manually through AWS console or CLI
   # Then run: terraform destroy
   ```

---

## Troubleshooting

### Error: "Wrong AWS account"
```
ERROR: Wrong AWS account! Expected 353695642481, got 123456789012
```
**Solution**: Update your AWS credentials or modify the account ID check in the workflow.

### Error: Lambda zip not found
```
Error: filebase64sha256(...) - open ../../dist/lambda.zip: no such file or directory
```
**Solution**: Ensure "Build Lambda zip" step completed successfully. Check Python requirements installation.

### Error: Terraform backend initialization fails
```
Error: error configuring S3 Backend: error validating provider credentials: error calling sts:GetCallerIdentity
```
**Solution**: 
- Verify AWS credentials are correctly configured
- Ensure IAM user/role has S3 and DynamoDB permissions
- Check backend bucket name matches region constraints

### Error: GitHub OIDC provider fails
```
Error: error creating IAM OIDC Provider: error getting GitHub OIDC certificate
```
**Solution**: Check network connectivity or GitHub API availability.

---

## File Changes Made

✅ **[terraform.tfvars.production](infra/terraform/terraform.tfvars.production)**
- Removed hardcoded `github_client_id`, `github_client_secret`, `jwt_secret`
- These are now passed via GitHub Actions environment variables (`TF_VAR_*`)
- Added comments explaining where secrets come from

---

## Local Testing (Without Bootstrap)

To test Terraform locally with LocalStack (no AWS required):

```bash
cd infra/terraform

# Set required variables
export TF_VAR_github_client_id="test-oauth-id"
export TF_VAR_github_client_secret="test-oauth-secret"
export TF_VAR_jwt_secret="test-jwt-secret"
export TF_VAR_use_localstack=true

# Initialize with local backend (skip S3)
terraform init

# Plan without AWS credentials
terraform plan
```

---

## Security Notes

- ⚠️ Never commit secrets to version control
- ⚠️ The temporary AWS credentials should be rotated and deleted after OIDC setup completes
- ⚠️ GitHub OIDC role should have minimal permissions (follow principle of least privilege)
- ⚠️ The bootstrap workflow should be deleted after one successful run

---

## Next Steps

1. **Set GitHub secrets** (all required secrets above)
2. **Run bootstrap workflow** and monitor for errors
3. **Complete OIDC transition** (as described in Step 4)
4. **Verify deployment** using `terraform-deploy.yml` workflow
