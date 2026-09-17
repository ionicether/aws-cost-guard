import boto3


def find(tag_key, tag_value):
    autoscaling = boto3.client("autoscaling")
    for page in autoscaling.get_paginator("describe_auto_scaling_groups").paginate():
        for group in page["AutoScalingGroups"]:
            tags = {t["Key"]: t["Value"] for t in group["Tags"]}
            if tags.get(tag_key) == tag_value and group["DesiredCapacity"] > 0:
                yield group["AutoScalingGroupARN"], {
                    "name": group["AutoScalingGroupName"],
                    "min_size": group["MinSize"],
                    "max_size": group["MaxSize"],
                    "desired_capacity": group["DesiredCapacity"],
                }


def pause(group_arn, snapshot):
    # Min size has to come down too or the group just launches replacements
    boto3.client("autoscaling").update_auto_scaling_group(
        AutoScalingGroupName=snapshot["name"], MinSize=0, DesiredCapacity=0
    )


def resume(group_arn, snapshot):
    boto3.client("autoscaling").update_auto_scaling_group(
        AutoScalingGroupName=snapshot["name"],
        MinSize=snapshot["min_size"],
        MaxSize=snapshot["max_size"],
        DesiredCapacity=snapshot["desired_capacity"],
    )
