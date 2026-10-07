import io
import json
from typing import Any

import numpy as np
import pytest
import soundfile

from app import sound_analyzer
from app.parrot_gate import ParrotGate

SAMPLE_RATE = 16000
RESULT_URL = "http://sqs/result"


def chirps(count: int, frequency: float = 5000.0) -> np.ndarray:
    silence = np.zeros(int(0.15 * SAMPLE_RATE))
    times = np.arange(int(0.12 * SAMPLE_RATE)) / SAMPLE_RATE
    parts = [silence]
    for _ in range(count):
        parts.extend([0.5 * np.sin(2 * np.pi * frequency * times), silence])
    return np.concatenate(parts).astype(np.float32)


SOUNDS = {
    "k/four": chirps(4),
    "k/silent": np.zeros(SAMPLE_RATE, dtype=np.float32),
    "k/mixed": np.concatenate([chirps(3), chirps(2, frequency=2000.0)]),
    "k/quiet": (chirps(4) * 0.001).astype(np.float32),
}


class FakeS3:
    def get_object(self, **params: str) -> dict[str, io.BytesIO]:
        body = io.BytesIO()
        soundfile.write(
            body, SOUNDS[params["Key"]], SAMPLE_RATE, format="WAV", subtype="FLOAT"
        )
        body.seek(0)
        return {"Body": body}


class FakeGate(ParrotGate):
    def __init__(self, *, is_parrot: bool = True) -> None:
        self.is_parrot = is_parrot
        self.calls = 0

    def predict(self, audio: np.ndarray, sample_rate: int) -> tuple[float, bool]:
        self.calls += 1
        return (0.9 if self.is_parrot else 0.2), self.is_parrot


class FakeSqs:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def send_message(self, **params: str) -> None:
        assert params["QueueUrl"] == RESULT_URL
        self.sent.append(json.loads(params["MessageBody"]))


@pytest.fixture(autouse=True)
def fake_s3(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIO_S3_BUCKET", "bucket")
    monkeypatch.setattr(sound_analyzer, "_s3", FakeS3())


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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-2")
    monkeypatch.setenv("SQS_JUDGMENT_RESULT_QUEUE_URL", RESULT_URL)
    monkeypatch.setattr(ParrotGate, "__init__", lambda self: None)
    from app import handler

    sqs = FakeSqs()
    monkeypatch.setattr(handler, "_gate", FakeGate())
    monkeypatch.setattr(handler, "_sqs", sqs)

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
        for body in sqs.sent
    ) == [("s1", 4), ("s3", 0)]


def test_call_count_includes_calls_outside_chirp_band() -> None:
    result = sound_analyzer.analyze(FakeGate(), "s1", "k/mixed")

    assert (result.call_count, result.chirp_count) == (5, 3)


def test_loud_sound_judged_not_parrot_counts_no_calls() -> None:
    result = sound_analyzer.analyze(FakeGate(is_parrot=False), "s1", "k/four")

    assert (result.is_parrot, result.call_count, result.chirp_count) == (False, 0, 0)


def test_too_quiet_sound_skips_gate() -> None:
    gate = FakeGate()

    results = [
        sound_analyzer.analyze(gate, "s1", "k/quiet"),
        sound_analyzer.analyze(gate, "s2", "k/four"),
    ]

    assert gate.calls == 1
    assert [(r.is_parrot, r.score, r.call_count, r.chirp_count) for r in results] == [
        (False, 0.0, 0, 0),
        (True, 0.9, 4, 4),
    ]
