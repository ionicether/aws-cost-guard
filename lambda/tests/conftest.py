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
            KeySchema=[{"AttributeName": "service_arn", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "service_arn", "AttributeType": "S"}],
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
