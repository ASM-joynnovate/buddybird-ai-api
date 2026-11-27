from types import ModuleType
from typing import Any

import pytest

from app.mimic_judgment import judgment
from tests.mimic_judgment.fakes import FakeMimicJudgmentModel


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.setattr(judgment, "load_model", FakeMimicJudgmentModel)

    from app.mimic_judgment import server

    monkeypatch.setattr(server, "_model", FakeMimicJudgmentModel())

    return server


def body(object_keys: list[str]) -> dict[str, Any]:
    return {
        "type": "audio.judge_mimic",
        "session_id": "session-1",
        "target": {"audio_id": "s1", "object_key": "q/sound.wav"},
        "reference": {"word_id": "w-1", "word_name": "안녕", "object_keys": object_keys},
    }


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
def test_judgment_is_returned_with_target_and_reference(
    server: ModuleType,
    object_keys: list[str],
    judgment: dict[str, Any],
) -> None:
    result = server.judge_mimic(body(object_keys))

    assert result["type"] == "audio.mimic_judged"
    assert result["session_id"] == "session-1"
    assert result["model_version"] == "parrot-mimicry-judgment@v1.0.1"
    assert result["target"] == {"audio_id": "s1"}
    assert result["reference"] == {"word_id": "w-1"}
    assert result["judgment"] == judgment


def test_missing_reference_fails(server: ModuleType) -> None:
    with pytest.raises(KeyError):
        server.judge_mimic(body(["missing/1.m4a"]))
