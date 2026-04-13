# Portfolio Builder Backend

FastAPI backend for the portfolio builder with AWS-native storage and Lambda support.

Responsibilities:
- GitHub OAuth login and callback handling
- Resume parsing and persistence to Amazon S3
- Slug and user metadata persistence in DynamoDB
- Slug management and public portfolio serving
- JWT session exchange and authenticated API routes

## Stack

- Auth: GitHub OAuth app
- API runtime: FastAPI (Docker locally), AWS Lambda + API Gateway in production
- Object storage: Amazon S3 (resume JSON and PDF files)
- Metadata store: Amazon DynamoDB (slug + user metadata)

Recommended frontend pairing in production: Cloudflare Pages.

## Required environment variables

Copy `.env.example` to `.env` and fill all values:

- `GITHUB_CLIENT_ID`
- `GITHUB_CLIENT_SECRET`
- `AWS_REGION`
- `AWS_S3_BUCKET`
- `AWS_DDB_TABLE`
- `AWS_S3_PREFIX`
- `JWT_SECRET`

Notes:
- GitHub OAuth callback URL must be `http://localhost:8000/api/auth/callback/github`
- In Lambda/API Gateway deployments, callback URL should be the API Gateway base URL plus `/api/auth/callback/github`
- `AWS_PUBLIC_BASE_URL` is optional (use CloudFront or custom domain for S3 objects)

## Local Docker run

1. Configure `.env` with GitHub + AWS credentials.
2. Start the backend:

```bash
./start-docker.sh
```

Stop it with:

```bash
./stop-docker.sh
```

Endpoints:
- API: http://localhost:8000
- Docs: http://localhost:8000/docs

## Lambda deployment notes

- Lambda handler entrypoint: `lambda_handler.handler`
- API Gateway should proxy all paths to the Lambda function
- For PDF uploads near 10MB, prefer pre-signed S3 upload flow to avoid gateway size constraints

## Terraform deployment (AWS)

Terraform files are in `infra/terraform` and provision:

- S3 bucket for resume/PDF storage
- DynamoDB table for slug/user metadata
- IAM role and policy for Lambda
- Lambda function for FastAPI
- API Gateway HTTP API with full proxy routes
- CloudWatch dashboard for API/Lambda/DynamoDB/S3/cost visibility
- CloudWatch alarms + SNS email notifications
- AWS Budget monthly threshold alerts

### 1. Build Lambda artifact

From this backend project directory:

```bash
rm -rf dist build && mkdir -p build/python dist
pip install -r requirements.txt -t build/python
cp -R app lambda_handler.py build/python/
cd build/python && zip -r ../../dist/lambda.zip . && cd ../..
```

### 2. Configure Terraform variables

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` with your values (frontend URL, GitHub OAuth credentials, JWT secret).
Also set:

- `alert_email` for alarms and budget notifications
- `monthly_budget_limit_usd` and `budget_alert_threshold_percent` for cost guardrails

### 3. Provision infrastructure

```bash
terraform init
terraform plan
terraform apply
```

### 4. Configure GitHub OAuth callback

After apply, set the callback URL in your GitHub OAuth app to the Terraform output `github_oauth_callback_url`.

For the deployed environment:

- GitHub OAuth Homepage URL: https://app.portfolio.handytools.work
- GitHub OAuth Authorization callback URL: https://api.portfolio.handytools.work/api/auth/callback/github

### 5. Point frontend to deployed API

Set `window.__PB_API_BASE__` in `portfolio-builder-frontend/config.js`:

```js
window.__PB_API_BASE__ = "https://api.portfolio.handytools.work";
```

Also ensure Terraform variable `frontend_url` exactly matches your Pages origin:

- `frontend_url = "https://app.portfolio.handytools.work"`

### 6. Confirm monitoring notifications

- Confirm the SNS email subscription from AWS (you will receive a confirmation email)
- Verify CloudWatch dashboard using output `cloudwatch_dashboard_name`
- Check budget/alarms after first few invocations

### 7. Optional: backend custom domain

Deployed custom domains:

- API: `api.portfolio.handytools.work`
  - ACM ARN: `arn:aws:acm:ap-southeast-1:353695642481:certificate/99d6a8c6-3073-4615-81fd-58ea41774f76`
- Portfolio pages: `portfolio.handytools.work`
  - ACM ARN: `arn:aws:acm:ap-southeast-1:353695642481:certificate/246d6dd5-c6c4-4f35-a7d2-9328cc96b745`

DNS CNAME records required in Cloudflare:
- `api.portfolio` → Terraform output `api_custom_domain_target`
- `portfolio` → Terraform output `portfolio_custom_domain_target`

## Main API routes

- `GET /api/auth/github`
- `GET /api/auth/callback/github`
- `GET /api/auth/exchange`
- `GET /api/resume`
- `POST /api/resume/upload`
- `POST /api/resume/pdf`
- `PUT /api/portfolio/slug`
- `GET /{slug}/`
