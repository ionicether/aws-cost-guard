import boto3
import pytest

from cost_guard import app


def paused_arns():
    return {item["service_arn"] for item in boto3.resource("dynamodb").Table("cost-guard-state").scan()["Items"]}


def desired_count(name):
    return boto3.client("ecs").describe_services(cluster="apps", services=[name])["services"][0]["desiredCount"]


def test_dry_run_changes_nothing(monkeypatch, service):
    monkeypatch.setenv("MODE", "dry_run")
    arn = service("web")

    out = app.handler({}, None)

    assert out["lines"] == [f"would pause {arn} (currently 2)"]
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
    assert out["lines"] == [f"restored {arn}"]
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
    from botocore.exceptions import ClientError

    arn = service("web")

    def refuse(*args):
        raise ClientError({"Error": {"Code": "AccessDeniedException", "Message": "nope"}}, "UpdateService")

    monkeypatch.setattr(app.ecs, "pause", refuse)

    out = app.handler({}, None)

    assert out["subject"] == "cost-guard paused 0 service(s)"
    assert out["lines"][0].startswith(f"FAILED to pause {arn}")
    assert paused_arns() == set()
