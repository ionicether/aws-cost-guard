terraform {
  # mock_provider in terraform test needs 1.7
  required_version = ">= 1.7"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.20" # python3.14 runtime
    }
    archive = {
      source  = "hashicorp/archive"
      version = ">= 2.8"
    }
  }
}
