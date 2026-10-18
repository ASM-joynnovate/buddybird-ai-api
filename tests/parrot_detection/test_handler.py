import json
from types import ModuleType
from typing import Any

import pytest

from app.parrot_detection.model import ParrotDetectionModel
from tests.parrot_detection.fakes import FakeParrotDetectionModel


@pytest.fixture
def handler(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.setattr(ParrotDetectionModel, "__init__", lambda _self: None)

    from app.parrot_detection import handler

    monkeypatch.setattr(handler, "_model", FakeParrotDetectionModel())

    return handler


def record(message_id: str, audio_id: str, object_key: str) -> dict[str, Any]:
    body = {
        "type": "audio.detect_parrot",
        "session_id": "session-1",
        "data": [{"audio_id": audio_id, "object_key": object_key, "captured_at": "2026-10-06T10:00:00+00:00"}],
    }

    return {"messageId": message_id, "body": json.dumps(body)}


def test_failed_sound_is_reported_and_others_are_published(
    handler: ModuleType,
    results: list[dict[str, Any]],
) -> None:
    records = [record("m-1", "s1", "k/four"), record("m-2", "s2", "k/missing"), record("m-3", "s3", "k/silent")]

    response = handler.handler({"Records": records}, None)

    assert response == {"batchItemFailures": [{"itemIdentifier": "m-2"}]}
    assert sorted((body["data"][0]["audio_id"], body["data"][0]["chirp_count"]) for body in results) == [
        ("s1", 4),
        ("s3", 0),
    ]
    assert {body["model_version"] for body in results} == {"parrot-sound-gate@v2.0.0"}
    assert all("analyzer_version" not in body for body in results)
