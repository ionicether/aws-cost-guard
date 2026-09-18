mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "123456789012"
    }
  }

  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    }
  }
}

variables {
  monthly_budget_usd = 50
}

run "defaults_to_dry_run" {
  command = plan

  assert {
    condition     = aws_lambda_function.this.environment[0].variables.MODE == "dry_run"
    error_message = "A fresh install must not pause anything until mode is set to enforce."
  }
}

run "passes_opt_in_tag_to_the_function" {
  command = plan

  variables {
    opt_in_tag = { key = "Team", value = "sandbox" }
  }

  assert {
    condition     = aws_lambda_function.this.environment[0].variables.TAG_KEY == "Team"
    error_message = "TAG_KEY does not match opt_in_tag.key."
  }

  assert {
    condition     = aws_lambda_function.this.environment[0].variables.TAG_VALUE == "sandbox"
    error_message = "TAG_VALUE does not match opt_in_tag.value."
  }
}

run "budget_fires_on_actual_spend_only" {
  command = plan

  assert {
    condition     = alltrue([for n in aws_budgets_budget.this.notification : n.notification_type == "ACTUAL"])
    error_message = "Forecasts are too noisy to pause resources on."
  }
}

run "rejects_unknown_mode" {
  command = plan

  variables {
    mode = "yolo"
  }

  expect_failures = [var.mode]
}
