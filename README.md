# terraform-aws-cost-guard

Pauses opted-in ECS services when monthly AWS spend crosses a budget. Starts in dry-run mode, so it only reports what it would do until you set `mode = "enforce"`.
