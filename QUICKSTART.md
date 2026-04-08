# Portfolio Builder - Local Development Quick Start

## 🚀 Super Quick Start (5 minutes)

```bash
cd /Users/Jaani.Nickolas/Documents/projects/portfolio-builder-backend

# 1️⃣  Setup (one-time)
chmod +x setup-local.sh && ./setup-local.sh

# 2️⃣  Start services in terminal 1
docker-compose up

# 3️⃣  In terminal 2, provision infrastructure
cd infra/terraform
terraform apply -var-file=terraform.tfvars.local

# 4️⃣  Test
curl http://localhost:8000/api/health
open http://localhost:8000/docs
```

## 📊 Architecture at a Glance

```
LocalStack (Docker)          Backend (FastAPI)           You
   ┌──────────┐                ┌──────────┐            
   │ S3       │◄──────────────►│          │
   │ DynamoDB │◄──────────────►│ FastAPI  │◄────► http://localhost:8000
   │ Lambda   │                │ Uvicorn  │
   │ API GW   │                │          │
   └──────────┘                └──────────┘
   :4566                       :8000
```

**Terraform provisions** everything on LocalStack.

## 🎯 Command Reference

### Get Running Quickly
| Goal | Command |
|------|---------|
| Full setup + start | `make setup && make up-d` |
| Just start services | `make up` |
| Provision infrastructure | `make terraform-apply` |
| Stop everything | `make down` |
| See all logs | `make logs` |

### Check Status
| Goal | Command |
|------|---------|
| Is API running? | `curl http://localhost:8000/api/health` |
| View API docs | `open http://localhost:8000/docs` |
| Container status | `make ps` |
| All info | `make info` |

### Inspect LocalStack
| Goal | Command |
|------|---------|
| List S3 buckets | `make ls-s3` |
| List DynamoDB tables | `make ls-dynamodb` |
| List Lambda functions | `make ls-lambda` |
| Terraform outputs | `make terraform-output` |

### Cleanup
| Goal | Command |
|------|---------|
| Rebuild cleanly | `make full-clean && make setup && make up-d && make terraform-apply` |
| Just reset state | `make terraform-clean` |
| Delete infrastructure | `make terraform-destroy` |

## 🔧 Configuration

**Environment Variables** (set in `docker-compose.yml` or shell):
```bash
GITHUB_CLIENT_ID=your-github-id         # Optional (for OAuth)
GITHUB_CLIENT_SECRET=your-github-secret # Optional (for OAuth)
JWT_SECRET=your-secret                  # Already set in docker-compose.yml
```

**Terraform Variables** (edit `terraform.tfvars.local`):
```hcl
use_localstack = true               # ← Use LocalStack
localstack_endpoint = "http://localhost:4566"
environment = "local"
# ... other vars
```

## 🧪 Common Workflows

### Test OAuth Flow
1. Set `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET`
2. Restart: `make restart`
3. Open http://localhost:8000/docs → Try `/auth/github`

### Upload a Resume
```bash
# 1. Get auth token (manual test)
curl http://localhost:8000/api/auth/me  # Will fail (need token)

# 2. Via docs: http://localhost:8000/docs → POST /upload
```

### Check Database
```bash
# S3 bucket contents
aws s3 ls s3://portfolio-builder-local --endpoint-url=http://localhost:4566

# DynamoDB items
aws dynamodb scan --table-name portfolio-builder-local-metadata \
  --endpoint-url=http://localhost:4566 --region us-east-1
```

### Debug Backend Code
```bash
# 1. Shell into container
make shell

# 2. Or view logs
make logs-backend

# 3. Code changes auto-reload (hot-reload enabled)
```

## ⚠️ Troubleshooting

| Problem | Solution |
|---------|----------|
| `docker: command not found` | Install Docker Desktop |
| Port 8000 in use | `lsof -i :8000` then `kill -9 <PID>` |
| LocalStack won't start | Wait 15s, check `make logs-localstack` |
| Terraform applies but nothing happens | Ensure LocalStack is healthy; check `make terraform-output` |
| Backend won't connect to S3 | Verify `AWS_ENDPOINT_URL=http://localstack:4566` |
| API docs page broken | Check backend logs: `make logs-backend` |

## 📚 Full Documentation

- **Setup guide**: See [LOCAL_DEV.md](./LOCAL_DEV.md)
- **Backend API**: http://localhost:8000/docs
- **Terraform**: [infra/terraform/README.md](./infra/terraform/README.md) *(if exists)*

## 🎓 Learning Path

1. **Start services**: `make up`
2. **Check OpenAPI docs**: http://localhost:8000/docs
3. **Provision infra**: `make terraform-apply`
4. **Inspect resources**: `make ls-s3`, `make ls-dynamodb`
5. **View state**: `make terraform-output`
6. **Test endpoints** via docs or `curl`
7. **Check logs**: `make logs`

## 🚨 When Things Go Wrong

```bash
# Nuclear option (clean reset)
make full-clean

# Then start fresh
make setup
make up-d
make terraform-apply
```

---

**Need help?** See [LOCAL_DEV.md](./LOCAL_DEV.md) for detailed documentation.
