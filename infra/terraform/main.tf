# Portfolio Builder Backend Infrastructure
# Deployed via GitHub Actions OIDC (no stored AWS credentials)

locals {
  name              = "${var.project_name}-${var.environment}"
  use_custom_domain = length(trimspace(var.api_custom_domain)) > 0
  api_base_url      = local.use_custom_domain ? "https://${var.api_custom_domain}" : aws_apigatewayv2_stage.default.invoke_url
}

resource "aws_s3_bucket" "portfolio" {
  bucket = "${local.name}-${data.aws_caller_identity.current.account_id}-${var.aws_region}"
}

resource "aws_s3_bucket_public_access_block" "portfolio" {
  bucket = aws_s3_bucket.portfolio.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "portfolio" {
  bucket = aws_s3_bucket.portfolio.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "portfolio" {
  bucket = aws_s3_bucket.portfolio.id

  rule {
    id     = "expire-old-resume-versions"
    status = "Enabled"

    filter {
      prefix = "${var.aws_s3_prefix}/users/"
    }

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}

resource "aws_dynamodb_table" "portfolio" {
  name         = "${local.name}-metadata"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"

  attribute {
    name = "pk"
    type = "S"
  }
}

data "aws_caller_identity" "current" {}

resource "aws_sns_topic" "alerts" {
  name = "${local.name}-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${local.name}-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "lambda_permissions" {
  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = ["arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*"]
  }

  statement {
    sid    = "S3Access"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject"
    ]
    resources = ["${aws_s3_bucket.portfolio.arn}/*"]
  }

  statement {
    sid    = "S3BucketRead"
    effect = "Allow"
    actions = [
      "s3:ListBucket",
      "s3:GetBucketLocation"
    ]
    resources = [aws_s3_bucket.portfolio.arn]
  }

  statement {
    sid    = "DynamoDBAccess"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:DeleteItem",
      "dynamodb:UpdateItem"
    ]
    resources = [aws_dynamodb_table.portfolio.arn]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "${local.name}-lambda-policy"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_permissions.json
}

resource "aws_lambda_function" "api" {
  function_name = "${local.name}-api"
  role          = aws_iam_role.lambda.arn
  handler       = "lambda_handler.handler"
  runtime       = "python3.12"
  filename      = var.lambda_zip_path
  timeout       = var.lambda_timeout
  memory_size   = var.lambda_memory_size

  source_code_hash = filebase64sha256(var.lambda_zip_path)

  environment {
    variables = {
      APP_BASE_URL           = local.api_base_url
      FRONTEND_URL           = var.frontend_url
      JWT_SECRET             = var.jwt_secret
      GITHUB_CLIENT_ID       = var.github_client_id
      GITHUB_CLIENT_SECRET   = var.github_client_secret
      AWS_REGION             = var.aws_region
      AWS_S3_BUCKET          = aws_s3_bucket.portfolio.bucket
      AWS_DDB_TABLE          = aws_dynamodb_table.portfolio.name
      AWS_S3_PREFIX          = var.aws_s3_prefix
      AWS_PUBLIC_BASE_URL    = var.aws_public_base_url
      PORTFOLIO_TEMPLATE_DIR = "/var/task/portfolio_template"
    }
  }
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${aws_lambda_function.api.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_apigatewayv2_api" "http" {
  name          = "${local.name}-http-api"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.http.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "root" {
  api_id    = aws_apigatewayv2_api.http.id
  route_key = "ANY /"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_route" "proxy" {
  api_id    = aws_apigatewayv2_api.http.id
  route_key = "ANY /{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_cloudwatch_log_group" "api_gateway" {
  count             = var.enable_api_gateway_access_logs ? 1 : 0
  name              = "/aws/apigateway/${local.name}"
  retention_in_days = var.log_retention_days
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.http.id
  name        = "$default"
  auto_deploy = true

  dynamic "access_log_settings" {
    for_each = var.enable_api_gateway_access_logs ? [1] : []
    content {
      destination_arn = aws_cloudwatch_log_group.api_gateway[0].arn
      format = jsonencode({
        requestId        = "$context.requestId"
        ip               = "$context.identity.sourceIp"
        requestTime      = "$context.requestTime"
        httpMethod       = "$context.httpMethod"
        routeKey         = "$context.routeKey"
        status           = "$context.status"
        protocol         = "$context.protocol"
        responseLength   = "$context.responseLength"
        integrationError = "$context.integration.error"
      })
    }
  }
}

resource "aws_apigatewayv2_domain_name" "custom" {
  count       = local.use_custom_domain ? 1 : 0
  domain_name = var.api_custom_domain

  domain_name_configuration {
    certificate_arn = var.api_acm_certificate_arn
    endpoint_type   = "REGIONAL"
    security_policy = "TLS_1_2"
  }

  lifecycle {
    precondition {
      condition     = length(trimspace(var.api_acm_certificate_arn)) > 0
      error_message = "api_acm_certificate_arn must be provided when api_custom_domain is set."
    }
  }
}

resource "aws_apigatewayv2_api_mapping" "custom" {
  count       = local.use_custom_domain ? 1 : 0
  api_id      = aws_apigatewayv2_api.http.id
  domain_name = aws_apigatewayv2_domain_name.custom[0].id
  stage       = aws_apigatewayv2_stage.default.id
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http.execution_arn}/*/*"
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  count               = var.enable_operational_alarms ? 1 : 0
  alarm_name          = "${local.name}-lambda-errors"
  alarm_description   = "Alarm when Lambda reports errors"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"

  dimensions = {
    FunctionName = aws_lambda_function.api.function_name
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "lambda_throttles" {
  count               = var.enable_operational_alarms ? 1 : 0
  alarm_name          = "${local.name}-lambda-throttles"
  alarm_description   = "Alarm when Lambda is throttled"
  namespace           = "AWS/Lambda"
  metric_name         = "Throttles"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"

  dimensions = {
    FunctionName = aws_lambda_function.api.function_name
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  count               = var.enable_operational_alarms ? 1 : 0
  alarm_name          = "${local.name}-api-5xx"
  alarm_description   = "Alarm when API Gateway returns server errors"
  namespace           = "AWS/ApiGateway"
  metric_name         = "5xx"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"

  dimensions = {
    ApiId = aws_apigatewayv2_api.http.id
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "ddb_throttles" {
  count               = var.enable_operational_alarms ? 1 : 0
  alarm_name          = "${local.name}-ddb-throttles"
  alarm_description   = "Alarm when DynamoDB request throttling occurs"
  namespace           = "AWS/DynamoDB"
  metric_name         = "ReadThrottleEvents"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"

  dimensions = {
    TableName = aws_dynamodb_table.portfolio.name
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "billing_estimated_charges" {
  count               = var.create_billing_alarm ? 1 : 0
  alarm_name          = "${local.name}-estimated-charges"
  alarm_description   = "Alarm when AWS estimated monthly charges exceed configured budget limit"
  namespace           = "AWS/Billing"
  metric_name         = "EstimatedCharges"
  statistic           = "Maximum"
  period              = 21600
  evaluation_periods  = 1
  threshold           = var.monthly_budget_limit_usd
  comparison_operator = "GreaterThanOrEqualToThreshold"

  dimensions = {
    Currency = "USD"
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
}

resource "aws_budgets_budget" "monthly" {
  count        = var.create_billing_alarm ? 1 : 0
  name         = "${local.name}-monthly-cost-budget"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_limit_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = var.budget_alert_threshold_percent
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.alert_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }
}

resource "aws_cloudwatch_dashboard" "operations" {
  count          = var.enable_operations_dashboard ? 1 : 0
  dashboard_name = "${local.name}-operations"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Lambda Invocations & Errors"
          region = var.aws_region
          period = 300
          stat   = "Sum"
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", aws_lambda_function.api.function_name],
            ["AWS/Lambda", "Errors", "FunctionName", aws_lambda_function.api.function_name],
            ["AWS/Lambda", "Throttles", "FunctionName", aws_lambda_function.api.function_name]
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "API Gateway 4xx / 5xx"
          region = var.aws_region
          period = 300
          stat   = "Sum"
          metrics = [
            ["AWS/ApiGateway", "4xx", "ApiId", aws_apigatewayv2_api.http.id],
            ["AWS/ApiGateway", "5xx", "ApiId", aws_apigatewayv2_api.http.id]
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "DynamoDB Read/Write Capacity"
          region = var.aws_region
          period = 300
          stat   = "Sum"
          metrics = [
            ["AWS/DynamoDB", "ConsumedReadCapacityUnits", "TableName", aws_dynamodb_table.portfolio.name],
            ["AWS/DynamoDB", "ConsumedWriteCapacityUnits", "TableName", aws_dynamodb_table.portfolio.name]
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "Lambda Duration (p50/p95/p99)"
          region = var.aws_region
          period = 300
          metrics = [
            [{ expression = "METRICS()", id = "e1", label = "Duration", period = 300 }],
            ["AWS/Lambda", "Duration", "FunctionName", aws_lambda_function.api.function_name, { id = "m1", stat = "p50" }],
            ["AWS/Lambda", "Duration", "FunctionName", aws_lambda_function.api.function_name, { id = "m2", stat = "p95" }],
            ["AWS/Lambda", "Duration", "FunctionName", aws_lambda_function.api.function_name, { id = "m3", stat = "p99" }]
          ]
        }
      }
    ]
  })
}
