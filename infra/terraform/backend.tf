terraform {
	backend "s3" {
		bucket         = "portfolio-builder-terraform-state-353695642481"
		key            = "prod/terraform.tfstate"
		region         = "ap-southeast-2"
		encrypt        = true
		dynamodb_table = "terraform-locks"
	}
}
