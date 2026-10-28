import json
from types import ModuleType
from typing import Any

import pytest

from app.mimic_judgment import judgment
from tests.mimic_judgment.fakes import FakeMimicJudgmentModel


@pytest.fixture
def handler(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.setattr(judgment, "load_model", FakeMimicJudgmentModel)

    from app.mimic_judgment import handler

    monkeypatch.setattr(handler, "_model", FakeMimicJudgmentModel())

    return handler


def record(message_id: str, object_keys: list[str]) -> dict[str, Any]:
    body = {
        "type": "audio.judge_mimic",
        "session_id": "session-1",
        "target": {"audio_id": "s1", "object_key": "q/sound.wav"},
        "reference": {"word_id": "w-1", "word_name": "안녕", "object_keys": object_keys},
    }

    return {"messageId": message_id, "body": json.dumps(body)}


@pytest.mark.parametrize(
    ("object_keys", "judgment"),
    [
        (
            ["r/1.m4a", "r/2.wav"],
            {"status": "ok", "is_success": True, "score": 0.7647059999999968, "n_own": 2, "n_fill": 18, "set_size": 20},
        ),
        (
            [],
            {"status": "no_reference", "is_success": False, "score": None, "n_own": 0, "n_fill": 0, "set_size": 0},
        ),
    ],
)
def test_judgment_is_published_with_target_and_reference(
    handler: ModuleType,
    results: list[dict[str, Any]],
    object_keys: list[str],
    judgment: dict[str, Any],
) -> None:
    response = handler.handler({"Records": [record("m-1", object_keys)]}, None)

    assert response == {"batchItemFailures": []}

    [body] = results

    assert body["type"] == "audio.mimic_judged"
    assert body["session_id"] == "session-1"
    assert body["model_version"] == "parrot-mimicry-judgment@v1.0.1"
    assert body["target"] == {"audio_id": "s1"}
    assert body["reference"] == {"word_id": "w-1"}
    assert body["judgment"] == judgment


def test_missing_reference_fails_only_that_message(handler: ModuleType, results: list[dict[str, Any]]) -> None:
    response = handler.handler({"Records": [record("m-1", ["missing/1.m4a"]), record("m-2", ["r/1.m4a"])]}, None)

    assert response == {"batchItemFailures": [{"itemIdentifier": "m-1"}]}
    assert [body["judgment"]["status"] for body in results] == ["ok"]
