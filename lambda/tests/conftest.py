import boto3
import pytest
from moto import mock_aws

TAG = {"key": "CostGuard", "value": "enabled"}


@pytest.fixture(autouse=True)
def aws(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-west-2")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("MODE", "enforce")
    monkeypatch.setenv("TAG_KEY", TAG["key"])
    monkeypatch.setenv("TAG_VALUE", TAG["value"])
    monkeypatch.setenv("STATE_TABLE", "cost-guard-state")
    with mock_aws():
        boto3.client("dynamodb").create_table(
            TableName="cost-guard-state",
            KeySchema=[{"AttributeName": "resource_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "resource_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        monkeypatch.setenv("REPORT_TOPIC_ARN", boto3.client("sns").create_topic(Name="reports")["TopicArn"])
        yield


@pytest.fixture
def service():
    ecs = boto3.client("ecs")
    ecs.create_cluster(clusterName="apps")

    def make(name, tagged=True, desired=2):
        ecs.register_task_definition(
            family=name, containerDefinitions=[{"name": name, "image": "nginx", "memory": 128}]
        )
        return ecs.create_service(
            cluster="apps",
            serviceName=name,
            taskDefinition=name,
            desiredCount=desired,
            tags=[TAG] if tagged else [],
        )["service"]["serviceArn"]

    return make


@pytest.fixture
def asg_group():
    def make(name, tagged=True):
        boto3.client("ec2").create_launch_template(
            LaunchTemplateName=name, LaunchTemplateData={"ImageId": "ami-12345678", "InstanceType": "t3.micro"}
        )
        autoscaling = boto3.client("autoscaling")
        autoscaling.create_auto_scaling_group(
            AutoScalingGroupName=name,
            LaunchTemplate={"LaunchTemplateName": name},
            MinSize=1,
            MaxSize=4,
            DesiredCapacity=2,
            AvailabilityZones=["us-west-2a"],
            Tags=[{"Key": TAG["key"], "Value": TAG["value"], "PropagateAtLaunch": False}] if tagged else [],
        )
        return autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[name])["AutoScalingGroups"][0]

    return make
