output "api_base_url" {
  description = "Base URL for the API (custom domain when configured, otherwise default API Gateway invoke URL)"
  value       = local.api_base_url
}

output "github_oauth_callback_url" {
  description = "Set this callback URL in your GitHub OAuth app"
  value       = "${local.api_base_url}/api/auth/callback/github"
}

output "api_gateway_default_invoke_url" {
  description = "Default API Gateway invoke URL"
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "api_custom_domain_name" {
  description = "Configured custom API domain name (empty when not configured)"
  value       = local.use_custom_domain ? var.api_custom_domain : ""
}

output "api_custom_domain_target" {
  description = "DNS target for CNAME record when using custom API domain"
  value       = local.use_custom_domain ? aws_apigatewayv2_domain_name.custom[0].domain_name_configuration[0].target_domain_name : ""
}

output "api_custom_domain_hosted_zone_id" {
  description = "Hosted zone ID for API custom domain alias records"
  value       = local.use_custom_domain ? aws_apigatewayv2_domain_name.custom[0].domain_name_configuration[0].hosted_zone_id : ""
}

output "lambda_function_name" {
  description = "Lambda function name"
  value       = aws_lambda_function.api.function_name
}

output "s3_bucket_name" {
  description = "S3 bucket for resume and PDF storage"
  value       = aws_s3_bucket.portfolio.bucket
}

output "dynamodb_table_name" {
  description = "DynamoDB table for user and slug metadata"
  value       = aws_dynamodb_table.portfolio.name
}

output "alerts_sns_topic_arn" {
  description = "SNS topic ARN used for alarms and notifications"
  value       = aws_sns_topic.alerts.arn
}

output "cloudwatch_dashboard_name" {
  description = "CloudWatch dashboard name for operations and cost visibility"
  value       = aws_cloudwatch_dashboard.operations.dashboard_name
}
