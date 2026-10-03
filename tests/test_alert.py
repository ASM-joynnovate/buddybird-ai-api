import asyncio
import json
from pathlib import Path
from typing import Any, cast

import pytest

from app import main as app_main
from app.alert import SlackAlerts, slack_payload
from app.health import MAX_INFERENCE_FAILURES, HealthState


class FakePost:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.bodies: list[dict[str, Any]] = []

    def __call__(self, url: str, body: bytes) -> None:
        if self.fail:
            raise OSError("network down")
        self.bodies.append(json.loads(body))


def titles(post: FakePost) -> list[str]:
    return [body["text"] for body in post.bodies]


def test_payload_has_header_and_fields() -> None:
    payload = slack_payload("제목", {"환경": "prod"})

    assert payload["text"] == "제목"
    header, section = cast(list[dict[str, Any]], payload["blocks"])
    assert header["text"]["text"] == "제목"
    assert section["fields"] == [{"type": "mrkdwn", "text": "*환경*\nprod"}]


def test_send_includes_environment() -> None:
    post = FakePost()
    SlackAlerts("https://hook", environment="dev", post=post).send("t", {"a": "b"})

    [body] = post.bodies
    fields = body["blocks"][1]["fields"]
    assert {"type": "mrkdwn", "text": "*환경*\ndev"} in fields
    assert {"type": "mrkdwn", "text": "*a*\nb"} in fields


def test_send_without_webhook_or_with_network_error_does_not_raise() -> None:
    post = FakePost(fail=True)

    SlackAlerts(None, environment="dev", post=post).send("t")
    SlackAlerts("https://hook", environment="dev", post=post).send("t")


async def test_send_later_posts_from_thread() -> None:
    post = FakePost()
    alerts = SlackAlerts("https://hook", environment="dev", post=post)

    alerts.send_later("t")
    await asyncio.sleep(0.05)

    assert titles(post) == ["t"]


def test_inference_change_is_reported_once_at_limit_and_on_recovery() -> None:
    changes: list[tuple[bool, int]] = []
    state = HealthState(on_inference_change=lambda u, n: changes.append((u, n)))

    for _ in range(MAX_INFERENCE_FAILURES + 1):
        state.inference_failed()
    state.inference_succeeded()
    state.inference_failed()
    state.inference_succeeded()

    assert changes == [
        (True, MAX_INFERENCE_FAILURES),
        (False, MAX_INFERENCE_FAILURES + 1),
    ]


def test_main_sends_start_failure_alert(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    post = FakePost()
    monkeypatch.setenv("HEALTH_FILE", str(tmp_path / "health.json"))
    monkeypatch.delenv("SQS_PARROT_SOUND_DETECTION_QUEUE_URL", raising=False)
    monkeypatch.setattr(
        SlackAlerts,
        "from_env",
        classmethod(lambda cls: cls("https://hook", environment="prod", post=post)),
    )

    with pytest.raises(RuntimeError):
        app_main.main()

    assert titles(post) == ["ai-api 시작 실패"]
