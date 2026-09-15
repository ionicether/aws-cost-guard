terraform {
  required_version = ">= 1.7"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = "us-west-2"
}

module "cost_guard" {
  source = "../.."

  monthly_budget_usd  = 50
  notification_emails = ["you@example.com"]
}

output "dry_run_command" {
  value = module.cost_guard.dry_run_command
}
