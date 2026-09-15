import logging
import os

import boto3

from cost_guard import ecs

log = logging.getLogger()
log.setLevel(logging.INFO)


def handler(event, context):
    enforce = os.environ["MODE"] == "enforce" and not event.get("dry_run")
    lines = []
    for service_arn, snapshot in ecs.find(os.environ["TAG_KEY"], os.environ["TAG_VALUE"]):
        # No restore yet, so the old count goes in the report
        if enforce:
            ecs.pause(service_arn, snapshot)
            lines.append(f"paused {service_arn} (was {snapshot['desired_count']})")
        else:
            lines.append(f"would pause {service_arn} (currently {snapshot['desired_count']})")

    verb = "paused" if enforce else "would pause"
    subject = f"cost-guard {verb} {len(lines)} service(s)"
    report = "\n".join(lines) or "No tagged services matched."
    log.info("%s\n%s", subject, report)
    boto3.client("sns").publish(TopicArn=os.environ["REPORT_TOPIC_ARN"], Subject=subject[:100], Message=report)
    return {"subject": subject, "lines": lines}
