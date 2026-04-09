# GitHub OIDC Provider for Terraform CI/CD
# Allows GitHub Actions to assume an AWS role without storing credentials

data "tls_certificate" "github" {
  url = "https://token.actions.githubusercontent.com"
}

resource "aws_iam_openid_connect_provider" "github" {
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.github.certificates[0].sha1_fingerprint]
  url             = data.tls_certificate.github.url
}

# IAM role that GitHub Actions will assume
resource "aws_iam_role" "github_terraform" {
  name = "${local.name}-github-terraform-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = aws_iam_openid_connect_provider.github.arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          }
          StringLike = {
            "token.actions.githubusercontent.com:sub" = "repo:jaani-builds/portfolio-builder-backend:*"
          }
        }
      }
    ]
  })
}

# Policy for GitHub Actions to run Terraform
resource "aws_iam_role_policy" "github_terraform" {
  name = "${local.name}-github-terraform-policy"
  role = aws_iam_role.github_terraform.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "*"
        Resource = "*"
      }
    ]
  })
}

output "github_role_arn" {
  description = "ARN for GitHub Actions to assume for Terraform"
  value       = aws_iam_role.github_terraform.arn
}

output "github_oidc_provider_arn" {
  description = "GitHub OIDC provider ARN"
  value       = aws_iam_openid_connect_provider.github.arn
}
