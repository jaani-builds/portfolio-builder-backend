# Local Development Setup - Portfolio Builder Backend

This guide explains how to run the entire portfolio builder infrastructure locally using Terraform and LocalStack.

## Architecture

```
┌─────────────────────────────────────┐
│  Your Local Machine                 │
│  ┌──────────────────────────────┐   │
│  │ Docker Compose               │   │
│  │ ├─ LocalStack (AWS emulator) │   │
│  │ │  ├─ S3                     │   │
│  │ │  ├─ DynamoDB               │   │
│  │ │  ├─ Lambda                 │   │
│  │ │  ├─ API Gateway            │   │
│  │ │  └─ IAM                    │   │
│  │ └─ Backend (FastAPI)         │   │
│  │    └─ uvicorn server         │   │
│  └──────────────────────────────┘   │
│                                     │
│  Terraform                          │
│  └─ Provisions LocalStack services  │
└─────────────────────────────────────┘
```

## Prerequisites

- **Docker** & **Docker Compose** - for LocalStack and backend container
- **Terraform** >= 1.6.0 - for infrastructure provisioning
- **Python** >= 3.9 - for local Lambda packaging
- **Git** - for cloning and checking dependencies
- **macOS/Linux** - tested on both (Windows may need adjustments)

Install on macOS with Homebrew:
```bash
brew install docker docker-compose terraform python@3.12
# Start Docker Desktop manually or via: brew install --cask docker
```

## Quick Start

### 1. Run the Setup Script

The setup script will check dependencies, prepare the Lambda package, and initialize Terraform:

```bash
cd /Users/Jaani.Nickolas/Documents/projects/portfolio-builder-backend
chmod +x setup-local.sh
./setup-local.sh
```

### 2. Start LocalStack and Backend Services

```bash
cd /Users/Jaani.Nickolas/Documents/projects/portfolio-builder-backend

# If you have GitHub OAuth credentials:
docker-compose up

# Or with credentials from env:
GITHUB_CLIENT_ID=your-id GITHUB_CLIENT_SECRET=your-secret docker-compose up

# To run in background:
docker-compose up -d
```

**What starts:**
- LocalStack on `localhost:4566` (emulates AWS services)
- Backend API on `localhost:8000` (FastAPI)
- Hot-reloading enabled (changes to code auto-update)

**Wait for health check:**
```
localstack    | Running on http://0.0.0.0:4566
backend       | Uvicorn running on http://0.0.0.0:8000
```

### 3. Provision Infrastructure with Terraform

Open a **new terminal** in the terraform directory:

```bash
cd /Users/Jaani.Nickolas/Documents/projects/portfolio-builder-backend/infra/terraform

# Preview what will be created:
terraform plan -var-file=terraform.tfvars.local

# Apply to create S3, DynamoDB, Lambda, API Gateway, etc.:
terraform apply -var-file=terraform.tfvars.local
```

When prompted, confirm with `yes`. This creates:
- ✅ S3 bucket (portfolio-builder-local-*)
- ✅ DynamoDB table (portfolio-builder-local-metadata)
- ✅ Lambda function
- ✅ API Gateway (HTTP API)
- ✅ IAM roles and policies
- ✅ CloudWatch alarms and dashboard
- ✅ SNS topic for alerts

### 4. Test the Backend

```bash
# Health check
curl http://localhost:8000/api/health

# API documentation (interactive)
open http://localhost:8000/docs

# Get outputs from Terraform
cd infra/terraform
terraform output

# Example: GitHub OAuth callback URL
terraform output github_oauth_callback_url
```

## Configuration

### Environment Variables

Edit `docker-compose.yml` or set via environment:

| Variable | Default | Purpose |
|----------|---------|---------|
| `GITHUB_CLIENT_ID` | (empty) | GitHub OAuth app client ID |
| `GITHUB_CLIENT_SECRET` | (empty) | GitHub OAuth app client secret |
| `JWT_SECRET` | `supersecretkey...` | JWT signing secret |
| `AWS_S3_BUCKET` | `portfolio-builder-local` | S3 bucket name |
| `AWS_DDB_TABLE` | `portfolio-builder-local-metadata` | DynamoDB table name |

### Terraform Configuration

Local development uses `terraform.tfvars.local`. Key variables:

| Variable | Value | Purpose |
|----------|-------|---------|
| `use_localstack` | `true` | Enable LocalStack endpoints |
| `localstack_endpoint` | `http://localhost:4566` | LocalStack endpoint |
| `environment` | `local` | Environment name in resource names |
| `github_client_id` | (from tfvars) | GitHub OAuth (optional) |

**Customize:**
```bash
cd infra/terraform

# Copy and edit:
cp terraform.tfvars.local terraform.tfvars.local.custom

# Then apply with custom values:
terraform apply -var-file=terraform.tfvars.local.custom
```

## Common Tasks

### View Logs

```bash
# Backend service logs
docker-compose logs -f backend

# LocalStack service logs
docker-compose logs -f localstack

# Combined logs
docker-compose logs -f
```

### Inspect LocalStack Services

```bash
# List S3 buckets in LocalStack
aws s3 ls --endpoint-url=http://localhost:4566 --region us-east-1

# List DynamoDB tables
aws dynamodb list-tables --endpoint-url=http://localhost:4566 --region us-east-1

# View Lambda functions
aws lambda list-functions --endpoint-url=http://localhost:4566 --region us-east-1
```

### Restart Services

```bash
# Stop all services
docker-compose down

# Restart
docker-compose up

# Hard restart (remove volumes/state)
docker-compose down -v
docker-compose up
```

### Rebuild Backend Image

If you update dependencies in `requirements.txt`:

```bash
docker-compose down
docker-compose build --no-cache backend
docker-compose up
```

### Clean Terraform State

```bash
cd infra/terraform

# Remove all local AWS resources
terraform destroy -var-file=terraform.tfvars.local

# Clean Terraform state entirely (fresh start)
rm -rf .terraform terraform.tfstate terraform.tfstate.backup .terraform.lock.hcl
terraform init -upgrade
```

## Debugging

### Backend Won't Start

Check Docker logs:
```bash
docker-compose logs backend
```

Common issues:
- Port 8000 already in use: `lsof -i :8000` and `kill -9 <PID>`
- Missing dependencies: Rebuild with `docker-compose build --no-cache`
- LocalStack not healthy: Wait 10-15 seconds and retry

### Terraform Apply Fails

```bash
# Check Terraform formatting
terraform fmt -check infra/terraform/

# Validate configuration
terraform validate

# See detailed error output
terraform apply -var-file=terraform.tfvars.local -no-color 2>&1 | cat
```

### Lambda Won't Invoke

Ensure the zip file exists:
```bash
ls -lh dist/lambda.zip
```

If missing, rebuild:
```bash
./setup-local.sh
```

### S3 Operations Fail

Ensure the bucket exists in LocalStack:
```bash
aws s3api list-buckets --endpoint-url=http://localhost:4566 --region us-east-1
```

If empty, re-apply Terraform:
```bash
cd infra/terraform
terraform apply -var-file=terraform.tfvars.local
```

## Data Persistence

- **LocalStack data**: Stored in `/tmp/localstack/` (deleted on restart)
- **Backend data**: Volume mounted at `./data/` (persists across restarts)
- **Terraform state**: `.tfstate` files in `infra/terraform/` (persists)

To preserve LocalStack state across restarts, modify `docker-compose.yml`:
```yaml
volumes:
  - localstack_data:/tmp/localstack  # Add named volume

volumes:
  localstack_data:
```

## Troubleshooting Tips

| Issue | Solution |
|-------|----------|
| Port conflicts | Change ports in `docker-compose.yml` |
| Slow startup | LocalStack takes 10-15s to initialize |
| Stale modules | Run `terraform init -upgrade` |
| Permission denied | Run `chmod +x setup-local.sh` |
| Docker daemon not running | Start Docker Desktop |
| Out of disk space | Run `docker system prune` |

## Moving to Production

When ready to deploy to AWS:

1. Create a `terraform.tfvars` for production (no LocalStack)
2. Update `use_localstack = false` in vars
3. Ensure AWS credentials are configured: `aws configure`
4. Create ACM certificate for custom domain (if desired)
5. Apply: `terraform apply -var-file=terraform.tfvars`

For detailed steps, see [PRODUCTION_DEPLOYMENT.md](./README.md)

## Next Steps

- [ ] Test the `/docs` endpoint at http://localhost:8000/docs
- [ ] Try uploading a resume via the API
- [ ] Verify S3 bucket contains objects: `aws s3 ls --endpoint-url=...`
- [ ] Check DynamoDB items: `aws dynamodb scan --endpoint-url=...`
- [ ] Review Terraform outputs: `terraform output`
- [ ] Set up GitHub OAuth app for full testing (optional)

## Support

Encounter issues? Check:

1. **Docker/LocalStack issues**: See troubleshooting section above
2. **Terraform errors**: Run `terraform validate` and check syntax
3. **Backend errors**: Check logs with `docker-compose logs -f backend`
4. **AWS CLI access**: Ensure you have AWS CLI configured

For production deployment, refer to the backend's main [README.md](./README.md).
