import json
from types import ModuleType
from typing import Any

import pytest

from app.mimic.judgment import MimicJudgment
from app.parrot_sound.gate import ParrotGate
from tests.mimic.fakes import FakeMimic
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
    monkeypatch.setattr(MimicJudgment, "__init__", lambda self: None)
    from app import handler

    monkeypatch.setattr(handler, "_gate", FakeGate())
    monkeypatch.setattr(handler, "_mimic", FakeMimic())
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


def mimic_record(
    message_id: str, words: list[dict[str, Any]], species: str | None = None
) -> dict[str, Any]:
    body = {
        "type": "audio.judge_mimic",
        "session_id": "session-1",
        "account_id": "user-1",
        "species": species,
        "data": [{"audio_id": "s1", "object_key": "q/sound.wav", "words": words}],
    }
    return {"messageId": message_id, "body": json.dumps(body)}


def test_mimic_judgments_follow_request_word_order(handler: ModuleType) -> None:
    words = [
        {
            "word_id": "w-1",
            "name": "안녕",
            "reference_object_keys": ["r/1.m4a", "r/2.wav"],
        },
        {"word_id": "w-2", "name": "사랑해", "reference_object_keys": []},
    ]

    response = handler.handler(
        {"Records": [mimic_record("m-1", words, species="macaw")]}, None
    )

    assert response == {"batchItemFailures": []}
    [body] = handler._sqs.sent
    assert body["type"] == "audio.mimic_judged"
    assert body["model_version"] == "parrot-mimicry-judgment@v1.0.0"
    assert body["data"] == [
        {
            "audio_id": "s1",
            "judgments": [
                {
                    "word_id": "w-1",
                    "status": "ok",
                    "is_success": True,
                    "score": 99.5,
                    "n_own": 2,
                    "n_fill": 18,
                    "set_size": 20,
                },
                {
                    "word_id": "w-2",
                    "status": "no_reference",
                    "is_success": False,
                    "score": None,
                    "n_own": 0,
                    "n_fill": 0,
                    "set_size": 0,
                },
            ],
        }
    ]


def test_mimic_missing_reference_fails_only_that_message(
    handler: ModuleType,
) -> None:
    response = handler.handler(
        {
            "Records": [
                mimic_record(
                    "m-1",
                    [
                        {
                            "word_id": "w-1",
                            "name": "안녕",
                            "reference_object_keys": ["missing/1.m4a"],
                        }
                    ],
                ),
                record("m-2", "s2", "k/four"),
            ]
        },
        None,
    )

    assert response == {"batchItemFailures": [{"itemIdentifier": "m-1"}]}
    assert [body["type"] for body in handler._sqs.sent] == ["audio.parrot_detected"]
