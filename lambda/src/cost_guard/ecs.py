import boto3


def find(tag_key, tag_value):
    ecs = boto3.client("ecs")
    for page in ecs.get_paginator("list_clusters").paginate():
        for cluster in page["clusterArns"]:
            arns = [
                arn
                for services in ecs.get_paginator("list_services").paginate(cluster=cluster)
                for arn in services["serviceArns"]
            ]
            # describe_services accepts at most 10 services per call
            for i in range(0, len(arns), 10):
                described = ecs.describe_services(cluster=cluster, services=arns[i : i + 10], include=["TAGS"])
                for service in described["services"]:
                    tags = {t["key"]: t["value"] for t in service.get("tags", [])}
                    if service["status"] != "ACTIVE" or service["desiredCount"] == 0:
                        continue
                    if tags.get(tag_key) == tag_value:
                        yield service["serviceArn"], {"cluster": cluster, "desired_count": service["desiredCount"]}


def pause(service_arn, snapshot):
    boto3.client("ecs").update_service(cluster=snapshot["cluster"], service=service_arn, desiredCount=0)


def resume(service_arn, snapshot):
    boto3.client("ecs").update_service(
        cluster=snapshot["cluster"], service=service_arn, desiredCount=snapshot["desired_count"]
    )
