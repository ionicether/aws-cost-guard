data "aws_caller_identity" "current" {}

# Separate from the reports topic so the function's own messages can't re-trigger it
resource "aws_sns_topic" "trigger" {
  #checkov:skip=CKV_AWS_26:Budgets can only publish to topics encrypted with a customer managed key, which costs money in a tool meant to save it
  name = "${var.name}-trigger"
}

data "aws_iam_policy_document" "trigger_topic" {
  statement {
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.trigger.arn]

    principals {
      type        = "Service"
      identifiers = ["budgets.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:budgets::${data.aws_caller_identity.current.account_id}:*"]
    }
  }
}

resource "aws_sns_topic_policy" "trigger" {
  arn    = aws_sns_topic.trigger.arn
  policy = data.aws_iam_policy_document.trigger_topic.json
}

resource "aws_budgets_budget" "this" {
  name         = var.name
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = var.threshold_percent
    threshold_type            = "PERCENTAGE"
    notification_type         = "ACTUAL"
    subscriber_sns_topic_arns = [aws_sns_topic.trigger.arn]
  }

  depends_on = [aws_sns_topic_policy.trigger]
}

resource "aws_sns_topic" "reports" {
  #checkov:skip=CKV_AWS_26:Reports name resource ARNs and nothing sensitive
  name = "${var.name}-reports"
}

resource "aws_sns_topic_subscription" "email" {
  for_each = toset(var.notification_emails)

  topic_arn = aws_sns_topic.reports.arn
  protocol  = "email"
  endpoint  = each.value
}

resource "aws_dynamodb_table" "state" {
  #checkov:skip=CKV_AWS_119:Encrypted at rest by default with an AWS owned key
  name         = "${var.name}-state"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "resource_id"

  attribute {
    name = "resource_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }
}

data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/src"
  output_path = "${path.module}/build/cost_guard.zip"
  excludes    = ["**/__pycache__/**"]
}

resource "aws_cloudwatch_log_group" "lambda" {
  #checkov:skip=CKV_AWS_158:Log groups are encrypted by default
  #checkov:skip=CKV_AWS_338:A year of logs for a function that runs monthly is not worth paying for
  name              = "/aws/lambda/${var.name}"
  retention_in_days = 30
}

resource "aws_lambda_function" "this" {
  #checkov:skip=CKV_AWS_50:Tracing adds cost and little insight for a function that runs a few times a month
  #checkov:skip=CKV_AWS_115:Reserving concurrency fails on accounts at or near the unreserved minimum, including many new ones
  #checkov:skip=CKV_AWS_117:Only calls AWS APIs, and a VPC would need NAT or endpoints that cost money
  #checkov:skip=CKV_AWS_173:Environment variables hold no secrets
  #checkov:skip=CKV_AWS_272:Code is built from this repository by Terraform
  function_name    = var.name
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.14"
  handler          = "cost_guard.app.handler"
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  timeout          = 900

  # SNS invokes asynchronously, so without this a crash goes unreported
  dead_letter_config {
    target_arn = aws_sns_topic.reports.arn
  }

  environment {
    variables = {
      MODE             = var.mode
      TAG_KEY          = var.opt_in_tag.key
      TAG_VALUE        = var.opt_in_tag.value
      STATE_TABLE      = aws_dynamodb_table.state.name
      REPORT_TOPIC_ARN = aws_sns_topic.reports.arn
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}

resource "aws_sns_topic_subscription" "lambda" {
  topic_arn = aws_sns_topic.trigger.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.this.arn

  # Without this the subscription can land before the function will accept it
  depends_on = [aws_lambda_permission.trigger]
}

resource "aws_lambda_permission" "trigger" {
  statement_id  = "AllowBudgetTopic"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.this.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.trigger.arn
}
