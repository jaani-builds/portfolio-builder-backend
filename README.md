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

## Environment setup

Copy `.env.example` to `.env` and provide the required values for your environment.

Use `.env.example` as the reference for the supported variables.

Notes:
- GitHub OAuth callback URL must be `http://localhost:8000/api/auth/callback/github`
- In deployed environments, the callback URL should be your public API base URL plus `/api/auth/callback/github`

## Local Docker run

1. Configure `.env`.
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

## Deployment notes

- Lambda handler entrypoint: `lambda_handler.handler`
- API Gateway should proxy all paths to the Lambda function
- For PDF uploads near 10MB, prefer pre-signed S3 upload flow to avoid gateway size constraints

## Infrastructure

Terraform configuration lives in `infra/terraform`.

Typical deployment flow:

```bash
cd infra/terraform
terraform init
terraform plan
terraform apply
```

After deployment, update your GitHub OAuth app to use your deployed API callback URL and point the frontend at the deployed API base.

## Main API routes

- `GET /api/auth/github`
- `GET /api/auth/callback/github`
- `GET /api/auth/exchange`
- `GET /api/resume`
- `POST /api/resume/upload`
- `POST /api/resume/pdf`
- `PUT /api/portfolio/slug`
- `GET /{slug}/`
