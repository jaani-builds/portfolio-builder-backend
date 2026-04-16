variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Base project name used in resource naming"
  type        = string
  default     = "portfolio-builder"
}

variable "environment" {
  description = "Deployment environment name"
  type        = string
  default     = "dev"
}

variable "frontend_url" {
  description = "Frontend URL for OAuth callback redirect back to UI"
  type        = string
}

variable "github_client_id" {
  description = "GitHub OAuth app client ID"
  type        = string
}

variable "github_client_secret" {
  description = "GitHub OAuth app client secret"
  type        = string
  sensitive   = true
}

variable "google_client_id" {
  description = "Google OAuth client ID"
  type        = string
  default     = ""
}

variable "google_client_secret" {
  description = "Google OAuth client secret"
  type        = string
  sensitive   = true
  default     = ""
}

variable "linkedin_client_id" {
  description = "LinkedIn OAuth client ID"
  type        = string
  default     = ""
}

variable "linkedin_client_secret" {
  description = "LinkedIn OAuth client secret"
  type        = string
  sensitive   = true
  default     = ""
}

variable "apple_client_id" {
  description = "Apple Sign In service ID"
  type        = string
  default     = ""
}

variable "apple_client_secret" {
  description = "Apple Sign In client secret JWT"
  type        = string
  sensitive   = true
  default     = ""
}

variable "jwt_secret" {
  description = "JWT signing secret"
  type        = string
  sensitive   = true
}

variable "lambda_zip_path" {
  description = "Path to packaged Lambda zip artifact"
  type        = string
  default     = "../../dist/lambda.zip"
}

variable "lambda_memory_size" {
  description = "Lambda memory in MB"
  type        = number
  default     = 128
}

variable "lambda_timeout" {
  description = "Lambda timeout in seconds"
  type        = number
  default     = 15
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 3
}

variable "aws_s3_prefix" {
  description = "S3 key prefix used by the backend"
  type        = string
  default     = "portfolio-builder"
}

variable "aws_public_base_url" {
  description = "Optional public base URL for objects (for example CloudFront)"
  type        = string
  default     = ""
}

variable "alert_email" {
  description = "Email address to receive cost and operational alerts"
  type        = string
}

variable "monthly_budget_limit_usd" {
  description = "Monthly AWS cost budget in USD"
  type        = number
  default     = 10
}

variable "budget_alert_threshold_percent" {
  description = "Alert threshold percentage for monthly budget"
  type        = number
  default     = 80
}

variable "create_billing_alarm" {
  description = "Create EstimatedCharges alarm (requires billing metrics enabled, best in us-east-1)"
  type        = bool
  default     = true
}

variable "enable_api_gateway_access_logs" {
  description = "Enable API Gateway access logs to CloudWatch"
  type        = bool
  default     = false
}

variable "enable_operational_alarms" {
  description = "Enable CloudWatch operational alarms (Lambda/API/DynamoDB)"
  type        = bool
  default     = false
}

variable "enable_operations_dashboard" {
  description = "Enable CloudWatch dashboard"
  type        = bool
  default     = false
}

variable "api_custom_domain" {
  description = "Optional custom domain for API Gateway (for example api.example.com)"
  type        = string
  default     = ""
}

variable "api_acm_certificate_arn" {
  description = "ACM certificate ARN in the same region as API Gateway for the custom API domain"
  type        = string
  default     = ""
}

variable "portfolio_custom_domain" {
  description = "Optional custom domain for public portfolio pages (for example portfolio.example.com)"
  type        = string
  default     = ""
}

variable "portfolio_acm_certificate_arn" {
  description = "ACM certificate ARN in the same region as API Gateway for the portfolio custom domain"
  type        = string
  default     = ""
}

variable "use_localstack" {
  description = "Use LocalStack for local development instead of real AWS"
  type        = bool
  default     = false
}

variable "localstack_endpoint" {
  description = "LocalStack endpoint URL (e.g., http://localhost:4566)"
  type        = string
  default     = "http://localhost:4566"
}
