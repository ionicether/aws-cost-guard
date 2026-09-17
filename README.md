# terraform-aws-cost-guard

Pauses opted-in ECS services and Auto Scaling groups when monthly AWS spend crosses a budget, and puts them back the way they were.

A budget alert publishes to SNS, which invokes a Lambda. The function looks for ECS services and Auto Scaling groups carrying an opt-in tag, writes down what each one is currently running, and scales it to zero. Reports go to their own topic so the function's own messages can't re-trigger it.

Stopping spend when a budget blows is easy. Stopping it in a way you're willing to leave switched on is the harder part, so this only does things that can be undone, and only to resources carrying a tag you put there on purpose. It starts in dry-run mode and changes nothing until you set `mode = "enforce"`.

## Doesn't AWS Budgets already do this?

Partly. Budgets has actions built in: it can attach an IAM policy or an SCP, or stop EC2 and RDS instances, and those actions can be reversed afterward.

The catch is you list the exact instance IDs when you set the action up, so anything created later isn't covered until you go back and add it. And it only reaches EC2 and RDS, which leaves out ECS services, Auto Scaling groups, and Lambda.

This module finds resources by tag at the moment it runs, so a new service is covered as soon as someone tags it. And when it restores, it puts back the actual settings, so a service that was running three tasks comes back with three rather than just being switched on. RDS and Lambda aren't built yet.

## Usage

```hcl
module "cost_guard" {
  source = "github.com/you/terraform-aws-cost-guard"

  monthly_budget_usd  = 50
  notification_emails = ["you@example.com"]
}
```

Apply it, then confirm the subscription email SNS sends you. Nothing else arrives until you click it, and the module has no way to tell you that.

Tag something you're willing to have paused with `CostGuard = enabled`. For an ECS service, check the tag actually comes back from `describe-services --include TAGS`. An empty list means the account is still on short ECS ARNs, which don't carry tags at all. Services keep whatever format they were created with, so turning the setting on doesn't fix the ones you already have.

Then dry run it rather than waiting on a budget alert to find out whether any of this works:

```sh
$(terraform output -raw dry_run_command)
```

You want one line per tagged resource. If it finds nothing, the tag is the first suspect and the region is the second. Once that looks right, set `mode = "enforce"` and apply. To bring everything back:

```sh
$(terraform output -raw restore_command)
```

See `examples/basic`.

The opt-in tag is the whole safety model. Discovery runs against every cluster and Auto Scaling group in the region and the tag decides what's a candidate, so there's no exemption list to maintain and anything untagged is left alone by default. It also means the dry run tells you your blast radius exactly: the services it names are the services at risk, and the list is never longer than that.

## How restore works

Before pausing anything, the function writes its current settings to DynamoDB. For an ECS service that's the desired count; for an Auto Scaling group it's the min, max, and desired capacity, since dropping the desired count alone just makes the group launch replacements. The write only goes through if there's no record already, which matters more than it sounds like it should: if someone scales a service back up by hand and the budget fires again, a second snapshot would record whatever it happened to be at that moment rather than what it was originally. Keeping the first one means restore always has the real number.

If the pause call then fails, the record is deleted again. A record for something that was never paused is worse than no record at all, because restore would act on it later.

Restore scans the table, resets each resource using the handler for its kind, and deletes the record as it goes. Anything that fails keeps its record, so running it again picks up where it left off.

## Inputs

| Name | Default | Description |
|---|---|---|
| `monthly_budget_usd` | required | Monthly cost budget in USD |
| `threshold_percent` | `100` | Percent of the budget actual spend must exceed |
| `mode` | `"dry_run"` | `dry_run` or `enforce` |
| `opt_in_tag` | `{ key = "CostGuard", value = "enabled" }` | Tag a service needs to be eligible |
| `notification_emails` | `[]` | Emails subscribed to reports |
| `name` | `"cost-guard"` | Prefix for everything the module creates |

## Development

```sh
cd lambda
pip install -r requirements-dev.txt
pytest
```

The tests run against [moto](https://github.com/getmoto/moto), so they need no AWS account and no credentials. They cover the pause and restore round trip, the double-pause case, a pause that fails partway, and the dry run changing nothing.

What moto won't tell you is whether the IAM policy is sufficient, since it doesn't enforce permissions by default. That one only shows up in a real account.

## Limitations

Only ECS services and Auto Scaling groups, and only in the region the module is deployed to. RDS and Lambda are next. Anything in another region is invisible to it.

AWS refreshes budget data up to three times a day, usually 8 to 12 hours apart, so something can burn through half a day of money before the alert fires. Treat this as a backstop, not a circuit breaker.

A pause doesn't always hold either. A scaling policy can push things back up, and so can the next apply in whatever project owns them, unless the capacity sits in `ignore_changes`. Restore handles that badly: it sets everything back to the recorded numbers regardless of what the resource is doing now.

Upgrading from a version before Auto Scaling group support replaces the state table, because the key changed from a service ARN to a generic resource ID. Restore anything you have paused before you upgrade, or the records go with it.

Restore is all or nothing. There's no way to bring back one service and leave the rest paused short of deleting rows from the table by hand.

## License

MIT.
