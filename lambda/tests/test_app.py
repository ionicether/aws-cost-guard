import boto3
from botocore.exceptions import ClientError

from cost_guard import app


def paused_arns():
    return {
        item["resource_id"]
        for item in boto3.resource("dynamodb").Table("cost-guard-state").scan()["Items"]
    }


def desired_count(name):
    return boto3.client("ecs").describe_services(cluster="apps", services=[name])[
        "services"
    ][0]["desiredCount"]


def test_dry_run_changes_nothing(monkeypatch, service):
    monkeypatch.setenv("MODE", "dry_run")
    arn = service("web")

    out = app.handler({}, None)

    assert out["lines"] == [f"would pause ecs {arn}"]
    assert desired_count("web") == 2
    assert paused_arns() == set()


def test_dry_run_flag_overrides_enforce_mode(service):
    service("web")

    app.handler({"dry_run": True}, None)

    assert desired_count("web") == 2


def test_untagged_services_are_left_alone(service):
    service("web", tagged=False)

    out = app.handler({}, None)

    assert out["lines"] == []
    assert desired_count("web") == 2


def test_pause_then_restore(service):
    arn = service("web", desired=3)

    app.handler({}, None)
    assert desired_count("web") == 0
    assert paused_arns() == {arn}

    out = app.handler({"action": "restore"}, None)
    assert out["lines"] == [f"restored ecs {arn}"]
    assert desired_count("web") == 3
    assert paused_arns() == set()


def test_second_pause_keeps_the_original_count(service):
    service("web", desired=3)
    app.handler({}, None)
    boto3.client("ecs").update_service(cluster="apps", service="web", desiredCount=1)

    app.handler({}, None)
    assert desired_count("web") == 0

    app.handler({"action": "restore"}, None)
    assert desired_count("web") == 3


def test_failed_pause_leaves_no_state_behind(monkeypatch, service):
    arn = service("web")

    def refuse(*args):
        raise ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "nope"}},
            "UpdateService",
        )

    monkeypatch.setattr(app.ecs, "pause", refuse)

    out = app.handler({}, None)

    assert out["subject"] == "cost-guard paused 0 resource(s)"
    assert out["lines"][0].startswith(f"FAILED to pause ecs {arn}")
    assert paused_arns() == set()


def test_pause_then_restore_an_asg(asg_group):
    group = asg_group("workers")
    autoscaling = boto3.client("autoscaling")

    app.handler({}, None)

    paused = autoscaling.describe_auto_scaling_groups(
        AutoScalingGroupNames=["workers"]
    )["AutoScalingGroups"][0]
    assert (paused["MinSize"], paused["DesiredCapacity"]) == (0, 0)
    assert paused_arns() == {group["AutoScalingGroupARN"]}

    app.handler({"action": "restore"}, None)

    restored = autoscaling.describe_auto_scaling_groups(
        AutoScalingGroupNames=["workers"]
    )["AutoScalingGroups"][0]
    assert (restored["MinSize"], restored["MaxSize"], restored["DesiredCapacity"]) == (
        1,
        4,
        2,
    )
    assert paused_arns() == set()


def test_untagged_asg_is_left_alone(asg_group):
    asg_group("workers", tagged=False)

    app.handler({}, None)

    assert paused_arns() == set()


def test_both_kinds_in_one_run(service, asg_group):
    service("web")
    asg_group("workers")

    out = app.handler({}, None)

    assert out["subject"] == "cost-guard paused 2 resource(s)"
    assert {line.split()[1] for line in out["lines"]} == {"ecs", "asg"}


def test_long_reports_are_truncated_to_fit_sns(monkeypatch):
    monkeypatch.setattr(app, "MAX_MESSAGE_BYTES", 200)

    report = app.body([f"paused ecs service-{i}" for i in range(50)])

    assert len(report.encode()) <= 200
    assert report.endswith("the rest]")


def test_a_resource_is_left_alone_when_its_state_cannot_be_written(
    monkeypatch, service
):
    arn = service("web")

    class RefusingTable:
        def put_item(self, **kwargs):
            raise ClientError(
                {
                    "Error": {
                        "Code": "ProvisionedThroughputExceededException",
                        "Message": "slow down",
                    }
                },
                "PutItem",
            )

        def scan(self, **kwargs):
            return {"Items": []}

    monkeypatch.setattr(app, "state_table", RefusingTable)

    out = app.handler({}, None)

    assert out["lines"][0].startswith(f"FAILED to record ecs {arn}")
    assert desired_count("web") == 2
