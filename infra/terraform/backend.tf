terraform {
	backend "s3" {
		bucket         = "portfolio-builder-terraform-state"
		key            = "prod/terraform.tfstate"
		region         = "ap-southeast-2"
		encrypt        = true
		dynamodb_table = "terraform-locks"
	}
}
