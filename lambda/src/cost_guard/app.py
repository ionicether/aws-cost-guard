import json
import logging
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from cost_guard import asg, ecs

KINDS = {"asg": asg, "ecs": ecs}

log = logging.getLogger()
log.setLevel(logging.INFO)


def handler(event, context):
    if event.get("action") == "restore":
        lines = restore()
        subject = f"cost-guard restored {count_ok(lines)} resource(s)"
    else:
        enforce = os.environ["MODE"] == "enforce" and not event.get("dry_run")
        lines = pause(enforce)
        verb = "paused" if enforce else "would pause"
        subject = f"cost-guard {verb} {count_ok(lines)} resource(s)"

    report = "\n".join(lines) or "No tagged resources matched."
    log.info("%s\n%s", subject, report)
    boto3.client("sns").publish(TopicArn=os.environ["REPORT_TOPIC_ARN"], Subject=subject[:100], Message=report)
    return {"subject": subject, "lines": lines}


def pause(enforce):
    table = state_table()
    lines = []
    for kind, module in KINDS.items():
        try:
            targets = list(module.find(os.environ["TAG_KEY"], os.environ["TAG_VALUE"]))
        except ClientError as err:
            lines.append(f"FAILED to scan {kind}: {err}")
            continue

        for resource_id, snapshot in targets:
            if not enforce:
                lines.append(f"would pause {kind} {resource_id}")
                continue

            created = remember(table, kind, resource_id, snapshot)
            try:
                module.pause(resource_id, snapshot)
            except ClientError as err:
                if created:
                    table.delete_item(Key={"resource_id": resource_id})
                lines.append(f"FAILED to pause {kind} {resource_id}: {err}")
                continue
            lines.append(f"paused {kind} {resource_id}")
    return lines


def remember(table, kind, resource_id, snapshot):
    try:
        table.put_item(
            Item={
                "resource_id": resource_id,
                "kind": kind,
                "snapshot": json.dumps(snapshot),
                "paused_at": datetime.now(timezone.utc).isoformat(),
            },
            ConditionExpression="attribute_not_exists(resource_id)",
        )
    except ClientError as err:
        if err.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        # Someone scaled it back up after an earlier pause. The first snapshot
        # holds the real original settings, so keep it.
        return False
    return True


def restore():
    table = state_table()
    lines = []
    for item in scan(table):
        kind, resource_id = item["kind"], item["resource_id"]
        try:
            KINDS[kind].resume(resource_id, json.loads(item["snapshot"]))
        except ClientError as err:
            lines.append(f"FAILED to restore {kind} {resource_id}: {err}")
            continue
        table.delete_item(Key={"resource_id": resource_id})
        lines.append(f"restored {kind} {resource_id}")
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
