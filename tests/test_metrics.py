import json

import pytest

from app import metrics
from app.sound_analyzer import SoundResult


def result(
    *,
    is_parrot: bool = False,
    score: float = 0.0,
    call_count: int = 0,
    too_quiet: bool = False,
) -> SoundResult:
    return SoundResult(
        is_parrot=is_parrot,
        score=score,
        call_count=call_count,
        chirp_count=0,
        too_quiet=too_quiet,
    )


def test_emit_writes_batch_metrics_line(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_ENV", "dev")
    results = [
        result(is_parrot=True, score=0.9, call_count=4),
        result(score=0.1),
        result(too_quiet=True),
    ]

    metrics.emit(results, failures=1, elapsed_seconds=1.23456)

    assert json.loads(capsys.readouterr().out) == {
        "event": "batch_metrics",
        "env": "dev",
        "FailedSounds": 1,
        "Sounds": 3,
        "ParrotSounds": 1,
        "TooQuietSounds": 1,
        "CallCount": 4,
        "BatchSeconds": 1.235,
        "ScoreMean": 0.5,
        "ScoreStdDev": 0.4,
    }


def test_score_metrics_are_omitted_when_every_sound_is_too_quiet(
    capsys: pytest.CaptureFixture[str],
) -> None:
    metrics.emit([result(too_quiet=True)], failures=0, elapsed_seconds=0.1)

    record = json.loads(capsys.readouterr().out)
    assert "ScoreMean" not in record
    assert "ScoreStdDev" not in record
