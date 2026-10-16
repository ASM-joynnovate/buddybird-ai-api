import json
from types import ModuleType
from typing import Any

import pytest

from app.parrot_sound.gate import ParrotGate
from tests.parrot_sound.fakes import FakeGate

RESULT_URL = "http://sqs/result"


class FakeSqs:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def send_message(self, **params: str) -> None:
        assert params["QueueUrl"] == RESULT_URL
        self.sent.append(json.loads(params["MessageBody"]))


@pytest.fixture
def handler(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-2")
    monkeypatch.setenv("SQS_JUDGMENT_RESULT_QUEUE_URL", RESULT_URL)
    monkeypatch.setattr(ParrotGate, "__init__", lambda self: None)
    from app import handler

    monkeypatch.setattr(handler, "_gate", FakeGate())
    monkeypatch.setattr(handler, "_sqs", FakeSqs())
    return handler


def record(message_id: str, audio_id: str, object_key: str) -> dict[str, Any]:
    body = {
        "type": "audio.detect_parrot",
        "session_id": "session-1",
        "data": [
            {
                "audio_id": audio_id,
                "object_key": object_key,
                "captured_at": "2026-10-06T10:00:00+00:00",
            }
        ],
    }
    return {"messageId": message_id, "body": json.dumps(body)}


def test_failed_sound_is_reported_and_others_are_published(
    handler: ModuleType,
) -> None:
    response = handler.handler(
        {
            "Records": [
                record("m-1", "s1", "k/four"),
                record("m-2", "s2", "k/missing"),
                record("m-3", "s3", "k/silent"),
            ]
        },
        None,
    )

    assert response == {"batchItemFailures": [{"itemIdentifier": "m-2"}]}
    assert sorted(
        (body["data"][0]["audio_id"], body["data"][0]["chirp_count"])
        for body in handler._sqs.sent
    ) == [("s1", 4), ("s3", 0)]
