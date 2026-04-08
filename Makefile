.PHONY: help setup up down logs clean terraform-plan terraform-apply terraform-destroy test docs

help:
	@echo "Portfolio Builder Backend - Local Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make setup              - Initialize environment (one-time)"
	@echo ""
	@echo "Services:"
	@echo "  make up                 - Start LocalStack and backend"
	@echo "  make down               - Stop all services"
	@echo "  make restart            - Restart services"
	@echo "  make logs               - View service logs"
	@echo "  make logs-backend       - View backend logs only"
	@echo ""
	@echo "Infrastructure:"
	@echo "  make terraform-plan     - Preview infrastructure changes"
	@echo "  make terraform-apply    - Create infrastructure"
	@echo "  make terraform-destroy  - Remove infrastructure"
	@echo "  make terraform-clean    - Full reset (state + modules)"
	@echo ""
	@echo "Development:"
	@echo "  make test               - Run tests"
	@echo "  make docs               - Open API docs (http://localhost:8000/docs)"
	@echo "  make health             - Check API health"
	@echo "  make shell              - Open backend container shell"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean              - Remove dist, build, __pycache__"
	@echo "  make full-clean         - Clean everything (services, state, dist)"
	@echo ""

setup:
	@chmod +x setup-local.sh
	@./setup-local.sh

up:
	@echo "Starting LocalStack and backend..."
	@docker-compose up

up-d:
	@echo "Starting LocalStack and backend (background)..."
	@docker-compose up -d
	@echo "Services starting. Check status with: docker-compose ps"

down:
	@echo "Stopping services..."
	@docker-compose down

restart:
	@echo "Restarting services..."
	@docker-compose restart

logs:
	@docker-compose logs -f

logs-backend:
	@docker-compose logs -f backend

logs-localstack:
	@docker-compose logs -f localstack

clean:
	@echo "Cleaning build artifacts..."
	@rm -rf dist build __pycache__ .pytest_cache
	@find . -type f -name "*.pyc" -delete
	@find . -type d -name "__pycache__" -delete
	@echo "Clean complete"

# Terraform commands
terraform-plan:
	@echo "Planning Terraform changes..."
	@cd infra/terraform && terraform plan -var-file=terraform.tfvars.local

terraform-apply:
	@echo "Applying Terraform changes..."
	@cd infra/terraform && terraform apply -var-file=terraform.tfvars.local

terraform-destroy:
	@echo "Destroying infrastructure..."
	@cd infra/terraform && terraform destroy -var-file=terraform.tfvars.local

terraform-clean:
	@echo "Resetting Terraform state..."
	@cd infra/terraform && rm -rf .terraform terraform.tfstate* .terraform.lock.hcl && terraform init -upgrade

terraform-output:
	@cd infra/terraform && terraform output

# Development commands
test:
	@echo "Running tests..."
	@python -m pytest tests/ -v

test-coverage:
	@echo "Running tests with coverage..."
	@python -m pytest tests/ -v --cov=app --cov-report=html

health:
	@echo "Checking API health..."
	@curl -s http://localhost:8000/api/health | python -m json.tool || echo "API not responding"

docs:
	@echo "Opening API docs..."
	@open http://localhost:8000/docs || xdg-open http://localhost:8000/docs || echo "Visit http://localhost:8000/docs"

shell:
	@docker-compose exec backend /bin/bash

full-clean: down terraform-destroy terraform-clean clean
	@echo "Full cleanup complete"
	@echo "Run 'make setup' to reinitialize"

# AWS LocalStack commands
ls-s3:
	@echo "S3 Buckets:"
	@aws s3 ls --endpoint-url=http://localhost:4566 --region us-east-1 2>/dev/null || echo "(LocalStack not running)"

ls-dynamodb:
	@echo "DynamoDB Tables:"
	@aws dynamodb list-tables --endpoint-url=http://localhost:4566 --region us-east-1 --query 'TableNames' 2>/dev/null || echo "(LocalStack not running)"

ls-lambda:
	@echo "Lambda Functions:"
	@aws lambda list-functions --endpoint-url=http://localhost:4566 --region us-east-1 --query 'Functions[].FunctionName' 2>/dev/null || echo "(LocalStack not running)"

# Info commands
ps:
	@docker-compose ps

status:
	@echo "Service Status:"
	@docker-compose ps
	@echo ""
	@echo "API Health:"
	@curl -s http://localhost:8000/api/health | python -m json.tool || echo "API not responding"

info: terraform-output status

build:
	@echo "Building Lambda package..."
	@./setup-local.sh
	@echo "Packaging portfolio template into Lambda artifact..."
	@if [ -d "../../jaani-builds.github.io" ]; then \
		mkdir -p dist/portfolio_template; \
		cp ../../jaani-builds.github.io/index.html dist/portfolio_template/index.html; \
		cp -R ../../jaani-builds.github.io/assets dist/portfolio_template/assets; \
		echo "Portfolio template staged at dist/portfolio_template/"; \
	else \
		echo "WARNING: ../../jaani-builds.github.io not found — portfolio template not packaged"; \
	fi
