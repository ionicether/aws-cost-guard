import json
import logging
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from cost_guard import ecs

log = logging.getLogger()
log.setLevel(logging.INFO)


def handler(event, context):
    if event.get("action") == "restore":
        lines = restore()
        subject = f"cost-guard restored {count_ok(lines)} service(s)"
    else:
        enforce = os.environ["MODE"] == "enforce" and not event.get("dry_run")
        lines = pause(enforce)
        verb = "paused" if enforce else "would pause"
        subject = f"cost-guard {verb} {count_ok(lines)} service(s)"

    report = "\n".join(lines) or "No tagged services matched."
    log.info("%s\n%s", subject, report)
    boto3.client("sns").publish(TopicArn=os.environ["REPORT_TOPIC_ARN"], Subject=subject[:100], Message=report)
    return {"subject": subject, "lines": lines}


def pause(enforce):
    table = state_table()
    lines = []
    for service_arn, snapshot in ecs.find(os.environ["TAG_KEY"], os.environ["TAG_VALUE"]):
        if not enforce:
            lines.append(f"would pause {service_arn} (currently {snapshot['desired_count']})")
            continue

        created = remember(table, service_arn, snapshot)
        try:
            ecs.pause(service_arn, snapshot)
        except ClientError as err:
            if created:
                table.delete_item(Key={"service_arn": service_arn})
            lines.append(f"FAILED to pause {service_arn}: {err}")
            continue
        lines.append(f"paused {service_arn} (was {snapshot['desired_count']})")
    return lines


def remember(table, service_arn, snapshot):
    try:
        table.put_item(
            Item={
                "service_arn": service_arn,
                "snapshot": json.dumps(snapshot),
                "paused_at": datetime.now(timezone.utc).isoformat(),
            },
            ConditionExpression="attribute_not_exists(service_arn)",
        )
    except ClientError as err:
        if err.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        # Someone scaled it back up after an earlier pause. The first snapshot
        # holds the real original count, so keep it.
        return False
    return True


def restore():
    table = state_table()
    lines = []
    for item in scan(table):
        service_arn = item["service_arn"]
        try:
            ecs.resume(service_arn, json.loads(item["snapshot"]))
        except ClientError as err:
            lines.append(f"FAILED to restore {service_arn}: {err}")
            continue
        table.delete_item(Key={"service_arn": service_arn})
        lines.append(f"restored {service_arn}")
    return lines


def scan(table):
    kwargs = {}
    while True:
        page = table.scan(**kwargs)
        yield from page["Items"]
        if "LastEvaluatedKey" not in page:
            return
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def state_table():
    return boto3.resource("dynamodb").Table(os.environ["STATE_TABLE"])


def count_ok(lines):
    return sum(1 for line in lines if not line.startswith("FAILED"))
