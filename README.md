# terraform-aws-cost-guard

Pauses tagged ECS services and ASGs when your monthly AWS spend crosses a budget, then puts them back exactly as they were. 

>Admittedly niche. It's for accounts with workloads you'd rather have off than spendy.

Budget alert -> SNS -> Lambda. The function finds anything carrying the opt-in tag, records what it's running, and scales it to zero. Reports go to a second topic (not the one that triggers it, or it retriggers itself).

Killing spend when a budget blows is easy. Killing it in a way you'll leave switched on isn't. So nothing here deletes anything, and nothing gets touched unless you tagged it. Ships in dry-run mode.

## Doesn't AWS Budgets already do this?

Partially, yes. Budgets has actions built in. It can attach an IAM policy or an SCP, or stop EC2 and RDS instances, and you can reverse any of that afterward.

The catch: the policy actions block new spend but leave everything already running untouched, and the stop action only reaches instances you listed by ID up front (100 of them, max). Nothing in there pauses a workload it wasn't told about in advance. It's also EC2 and RDS only -> no ECS, no ASGs, no Lambda.

This finds things by tag at the moment it runs, so a new service is covered as soon as it's tagged. Restore puts back the real settings too (a service running 3 tasks comes back running 3, not just "on").

RDS and Lambda handlers aren't written yet.

## Usage

```hcl
module "cost_guard" {
  source = "github.com/you/terraform-aws-cost-guard"

  monthly_budget_usd  = 50
  notification_emails = ["you@example.com"]
}
```

Apply, then confirm the SNS subscription email. Nothing arrives until you do, and the module can't tell you that.

Tag something with `CostGuard = enabled`, then check the tag comes back:

```sh
aws ecs describe-services --cluster mycluster --services myservice \
  --include TAGS --query 'services[0].tags'
```

Empty list -> the account is still on short ECS ARNs. Those don't carry tags at all. Services keep whichever format they were created with, so flipping the account setting won't fix existing ones. Recreate them.

Dry run before you trust it:

```sh
$(terraform output -raw dry_run_command)
```

One line per tagged resource. Nothing at all is usually the tag, then the region. When it looks right, set `mode = "enforce"` and apply.

Restore:

```sh
$(terraform output -raw restore_command)
```

Full example in `examples/basic`.

The tag is the whole safety model. Discovery sweeps every cluster and ASG in the region, and the tag is the only thing that makes a resource a candidate. No exemption list, nothing to keep in sync, untagged is ignored. It also means the dry run is your blast radius: what it lists is what's at risk, and the list doesn't grow on its own.

## How restore works

Settings get written to DynamoDB before anything is paused. ECS is just the desired count. ASGs need min, max, and desired, because dropping desired alone does nothing (the group launches replacements to get back to min).

The write is conditional on no record existing. That matters more than it sounds like it should: someone scales a service back up by hand, the budget fires again a day later, and a fresh snapshot would record whatever it happened to be at that moment. Keeping the first one means restore still has the real number.

If the pause then fails, the record is deleted. A record for something that was never paused is worse than no record (restore acts on it later).

Restore walks the table, resets each resource through the handler for its kind, and deletes rows as it goes. Failures keep their row, so run it again.

## Inputs

| Name | Default | Description |
|---|---|---|
| `monthly_budget_usd` | required | Monthly cost budget in USD |
| `threshold_percent` | `100` | Percent of the budget actual spend must exceed |
| `mode` | `"dry_run"` | `dry_run` or `enforce` |
| `opt_in_tag` | `{ key = "CostGuard", value = "enabled" }` | Tag a resource needs to be eligible |
| `notification_emails` | `[]` | Emails subscribed to reports |
| `name` | `"cost-guard"` | Prefix for everything the module creates |

## When things go wrong

Settings can't be written -> the resource is left running and the report states it. Pausing something that can't be restored is worse than the spend.

A run that dies halfway leaves consistent state. Everything is recorded before it's touched, anything already paused is skipped next time, so invoking again carries on from where it stopped. You lose that run's report.

If the function crashes outright, the failed event lands on the reports topic instead of vanishing. That tells you something broke, not what. Logs for that.

Reports over the 256 KB SNS limit get truncated, with a pointer to the logs.

## Limitations

ECS and ASGs only, in one region (the one you deployed to). RDS and Lambda are next.

Budget data refreshes up to 3x a day, usually 8 to 12 hours apart. Something can burn half a day of money before the alert fires. Backstop, not a circuit breaker.

A pause doesn't always hold. Scaling policies push things back up, and so does the next apply in whatever project owns them, unless the capacity is in `ignore_changes`. Restore handles that badly: it resets to the recorded numbers regardless of what the resource is doing now.

Restore is all or nothing. One service back and the rest paused means deleting rows by hand.

Upgrading from before ASG support replaces the state table (the key changed from a service ARN to a generic resource ID). Restore anything paused first or the records go with it.

## Development

```sh
cd lambda
pip install -r requirements-dev.txt
pytest
```

Runs against [moto](https://github.com/getmoto/moto), so no AWS account and no credentials. Covers a pause/restore round trip for both resource types, the double-pause case, a pause that fails partway, a write that can't be recorded, and the dry run leaving everything alone.

Terraform has its own tests against a mocked provider:

```sh
terraform init -backend=false
terraform test
```

Those catch what a misconfigured module gets wrong quietly: fresh install in dry-run mode, the opt-in tag reaching the function, the budget firing on actual spend and not a forecast.

CI runs both suites plus tflint and Checkov. Every Checkov skip carries its reason inline, so you can disagree with it rather than wonder what got ignored.

None of it tells you whether the IAM policy is sufficient. Moto doesn't enforce permissions, so that only shows up in a real account.

## License

MIT.
