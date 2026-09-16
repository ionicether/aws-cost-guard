output "function_name" {
  value = aws_lambda_function.this.function_name
}

output "dry_run_command" {
  value = "aws lambda invoke --function-name ${aws_lambda_function.this.function_name} --cli-binary-format raw-in-base64-out --payload '{\"dry_run\": true}' /dev/stdout"
}

output "state_table_name" {
  description = "Holds the pre-pause desired count of every paused service."
  value       = aws_dynamodb_table.state.name
}

output "restore_command" {
  value = "aws lambda invoke --function-name ${aws_lambda_function.this.function_name} --cli-binary-format raw-in-base64-out --payload '{\"action\": \"restore\"}' /dev/stdout"
}
