output "function_name" {
  value = aws_lambda_function.this.function_name
}

output "dry_run_command" {
  value = "aws lambda invoke --function-name ${aws_lambda_function.this.function_name} --cli-binary-format raw-in-base64-out --payload '{\"dry_run\": true}' /dev/stdout"
}
