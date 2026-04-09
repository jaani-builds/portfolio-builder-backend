terraform {
  backend "s3" {
    bucket       = "portfolio-builder-terraform-state-353695642481-apse1"
    key          = "prod/terraform.tfstate"
    region       = "ap-southeast-1"
    encrypt      = true
    use_lockfile = true
  }
}
