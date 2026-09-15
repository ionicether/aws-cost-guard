# terraform-aws-cost-guard

Pauses opted-in ECS services when monthly AWS spend crosses a budget.

A budget alert publishes to SNS, which invokes a Lambda. The function looks for ECS services carrying an opt-in tag and sets their desired count to zero, then reports what it did to a second SNS topic. Reports go to their own topic so the function's own messages can't re-trigger it.

Stopping spend when a budget blows is easy. Stopping it in a way you're willing to leave switched on is the harder part, so this only does things that can be undone, and only to resources carrying a tag you put there on purpose. It starts in dry-run mode and changes nothing until you set `mode = "enforce"`.

## Doesn't AWS Budgets already do this?

>What follows is what I'm building toward, not what works today. See Limitations for where it actually is.

Partially, yes. Budgets has actions built in: it can attach an IAM policy or an SCP, or stop EC2 and RDS instances, and those actions can be reversed afterward.

The catch is you list the exact instance IDs when you set the action up, so anything created later isn't covered until you go back and add it. And it only reaches EC2 and RDS, which leaves out ECS services, Auto Scaling groups, and Lambda.

This module finds resources by tag at the moment it runs, so a new service is covered as soon as someone tags it. And when it restores, it puts back the actual settings, so a service that was running three tasks comes back with three rather than just being switched on.

## Usage

```hcl
module "cost_guard" {
  source = "github.com/you/terraform-aws-cost-guard"

  monthly_budget_usd  = 50
  notification_emails = ["you@example.com"]
}
```

Apply it, then confirm the subscription email SNS sends you. Nothing else arrives until you click it, and the module has no way to tell you that.

Tag a service you're willing to have paused with `CostGuard = enabled`, then check the tag actually comes back from `describe-services --include TAGS`. An empty list means the account is still on short ECS ARNs, which don't carry tags at all. Services keep whatever format they were created with, so turning the setting on doesn't fix the ones you already have.

Then dry run it rather than waiting on a budget alert to find out whether any of this works:

```sh
$(terraform output -raw dry_run_command)
```

You want one line per tagged service with its current count. If it finds nothing, the tag is the first suspect and the region is the second. Once that looks right, set `mode = "enforce"` and apply. See `examples/basic`.

The opt-in tag is the whole safety model. Discovery runs against every cluster in the region and the tag decides what's a candidate, so there's no exemption list to maintain and anything untagged is left alone by default. It also means the dry run tells you your blast radius exactly: the services it names are the services at risk, and the list is never longer than that.

## Inputs

| Name | Default | Description |
|---|---|---|
| `monthly_budget_usd` | required | Monthly cost budget in USD |
| `threshold_percent` | `100` | Percent of the budget actual spend must exceed |
| `mode` | `"dry_run"` | `dry_run` or `enforce` |
| `opt_in_tag` | `{ key = "CostGuard", value = "enabled" }` | Tag a service needs to be eligible |
| `notification_emails` | `[]` | Emails subscribed to reports |
| `name` | `"cost-guard"` | Prefix for everything the module creates |

## Limitations

There's no restore yet. The report carries each service's previous desired count, so putting things back is one `update-service` call away, but you make it yourself. Automatic restore is next, and after that Auto Scaling groups, RDS, and Lambda.

Only ECS services in the region the module is deployed to. Anything elsewhere is invisible to it.

AWS refreshes budget data up to three times a day, usually 8 to 12 hours apart, so something can burn through half a day of money before the alert fires. Treat this as a backstop, not a circuit breaker.

A pause doesn't always hold either. A scaling policy can push a service back up, and so can the next apply in whatever project owns it, unless the desired count sits in `ignore_changes`.

## License

MIT.
