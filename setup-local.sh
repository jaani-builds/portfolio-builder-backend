#!/bin/bash
set -euo pipefail

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR"
TERRAFORM_DIR="$SCRIPT_DIR/infra/terraform"

echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Portfolio Builder - Local Development Setup${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"

# Check dependencies
echo -e "\n${YELLOW}Checking dependencies...${NC}"

for cmd in docker docker-compose git terraform python3; do
  if ! command -v $cmd &> /dev/null; then
    echo -e "${RED}✗ $cmd is not installed${NC}"
    exit 1
  fi
done
echo -e "${GREEN}✓ All dependencies found${NC}"

# Check GitHub OAuth credentials
if [ -z "${GITHUB_CLIENT_ID:-}" ] || [ -z "${GITHUB_CLIENT_SECRET:-}" ]; then
  echo -e "\n${YELLOW}⚠ GitHub OAuth credentials not found in environment${NC}"
  echo "   Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET to enable OAuth login"
  echo "   You can still test the backend without OAuth"
fi

# Create data directory
echo -e "\n${YELLOW}Setting up directories...${NC}"
mkdir -p "$BACKEND_DIR/data"
mkdir -p "$TERRAFORM_DIR"
echo -e "${GREEN}✓ Directories ready${NC}"

# Prepare Lambda zip for local development
echo -e "\n${YELLOW}Preparing Lambda package...${NC}"
cd "$BACKEND_DIR"

# Remove old dist
rm -rf dist build
mkdir -p build/python dist

# Install dependencies
pip install -q -r requirements.txt -t build/python

# Copy app code
cp -R app lambda_handler.py build/python/

# Create deployment package
cd build/python
zip -q -r "../../dist/lambda.zip" .
cd "$BACKEND_DIR"

echo -e "${GREEN}✓ Lambda package created at dist/lambda.zip${NC}"

# Initialize Terraform
echo -e "\n${YELLOW}Initializing Terraform...${NC}"
cd "$TERRAFORM_DIR"
terraform init -upgrade
echo -e "${GREEN}✓ Terraform initialized${NC}"

# Show next steps
echo -e "\n${GREEN}════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Setup Complete!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"

echo -e "\n${BLUE}Step 1: Start LocalStack and Backend${NC}"
echo -e "   ${YELLOW}cd $BACKEND_DIR${NC}"
if [ -z "${GITHUB_CLIENT_ID:-}" ]; then
  echo -e "   ${YELLOW}GITHUB_CLIENT_ID=temp GITHUB_CLIENT_SECRET=temp docker-compose up${NC}"
else
  echo -e "   ${YELLOW}docker-compose up${NC}"
fi

echo -e "\n${BLUE}Step 2: In another terminal, provision local infrastructure${NC}"
echo -e "   ${YELLOW}cd $TERRAFORM_DIR${NC}"
echo -e "   ${YELLOW}terraform plan -var-file=terraform.tfvars.local${NC}"
echo -e "   ${YELLOW}terraform apply -var-file=terraform.tfvars.local${NC}"

echo -e "\n${BLUE}Step 3: Backend will be available at:${NC}"
echo -e "   ${YELLOW}API: http://localhost:8000${NC}"
echo -e "   ${YELLOW}Docs: http://localhost:8000/docs${NC}"

echo -e "\n${BLUE}Step 4: Test the API${NC}"
echo -e "   ${YELLOW}curl http://localhost:8000/api/health${NC}"

echo -e "\n${BLUE}Cleanup${NC}"
echo -e "   Stop services: ${YELLOW}docker-compose down${NC}"
echo -e "   Destroy infrastructure: ${YELLOW}terraform destroy -var-file=terraform.tfvars.local${NC}"
echo ""
