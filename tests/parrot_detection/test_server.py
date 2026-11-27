from types import ModuleType
from typing import Any

import pytest

from app.parrot_detection.model import ParrotDetectionModel
from tests.parrot_detection.fakes import FakeParrotDetectionModel


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.setattr(ParrotDetectionModel, "__init__", lambda _self: None)

    from app.parrot_detection import server

    monkeypatch.setattr(server, "_model", FakeParrotDetectionModel())

    return server


def body(object_key: str) -> dict[str, Any]:
    return {
        "type": "audio.detect_parrot",
        "session_id": "session-1",
        "data": [{"audio_id": "s1", "object_key": object_key, "captured_at": "2026-10-06T10:00:00+00:00"}],
    }


def test_detection_is_returned_as_result_message(server: ModuleType) -> None:
    result = server.detect_parrot(body("k/four"))

    assert result["type"] == "audio.parrot_detected"
    assert result["session_id"] == "session-1"
    assert result["model_version"] == "parrot-sound-gate@v2.0.1"
    assert result["data"] == [{"audio_id": "s1", "is_parrot": True, "score": 0.9, "call_count": 4, "chirp_count": 4}]


def test_missing_sound_fails(server: ModuleType) -> None:
    with pytest.raises(KeyError):
        server.detect_parrot(body("k/missing"))
