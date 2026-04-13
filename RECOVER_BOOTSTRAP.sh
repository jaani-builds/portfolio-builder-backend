#!/bin/bash

# Recovery script to import existing AWS resources into Terraform state
# Run this after fixing the Terraform configuration conflicts

set -euo pipefail

echo "🔧 Terraform Bootstrap Recovery Script"
echo "========================================"
echo ""
echo "This script imports existing AWS resources that were already created"
echo "during previous bootstrap attempts into the current Terraform state."
echo ""

cd infra/terraform

# Check if we're already initialized
if [ ! -d ".terraform" ]; then
  echo "⚠️  Terraform not initialized. Running 'terraform init'..."
  terraform init
fi

echo ""
echo "📦 Step 1: Import GitHub OIDC Provider"
echo "----------------------------------------"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
GITHUB_OIDC_ARN="arn:aws:iam::${ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
echo "Importing GitHub OIDC provider: $GITHUB_OIDC_ARN"

# Import the GitHub OIDC provider
terraform import 'aws_iam_openid_connect_provider.github' "$GITHUB_OIDC_ARN" || {
  echo "⚠️  Note: Failed to import GitHub OIDC - it may already be in state or not exist"
}

echo ""
echo "📦 Step 2: Import Lambda IAM Role"
echo "-----------------------------------"
LAMBDA_ROLE_NAME="portfolio-builder-prod-lambda-role"
echo "Importing Lambda role: $LAMBDA_ROLE_NAME"

# Import the Lambda IAM role
# The import ID for aws_iam_role is just the role name
terraform import 'aws_iam_role.lambda' "$LAMBDA_ROLE_NAME" || {
  echo "⚠️  Note: Failed to import Lambda role - it may already be in state"
}

echo ""
echo "📦 Step 3: Import AWS Budget"
echo "------------------------------"
BUDGET_NAME="portfolio-builder-prod-monthly-cost-budget"
echo "Importing budget: $BUDGET_NAME"

# Import the budget (if create_billing_alarm is true)
# The import ID for aws_budgets_budget is: account_id:budget_name
echo "Using AWS Account ID: $ACCOUNT_ID"

terraform import "aws_budgets_budget.monthly[0]" "$ACCOUNT_ID:$BUDGET_NAME" || {
  echo "⚠️  Note: Failed to import budget - check if billing alarms are enabled"
}

echo ""
echo "✅ Import Complete!"
echo ""
echo "Next steps:"
echo "1. Run 'terraform plan' to verify the state matches your AWS resources"
echo "2. If there are any mismatches, resolve them manually"
echo "3. Run 'terraform apply' to proceed with any pending infrastructure changes"
echo ""
echo "To run this recovery:"
echo "  cd portfolio-builder-backend"
echo "  bash RECOVER_BOOTSTRAP.sh"
echo ""
