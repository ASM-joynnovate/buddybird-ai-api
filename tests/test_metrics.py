import json

import pytest

from app import metrics
from app.onset.application.cycle_analyzer import CaptureResult


def result(
    *,
    is_parrot: bool = False,
    probability: float = 0.0,
    call_count: int = 0,
    too_quiet: bool = False,
    is_emergency: bool = False,
) -> CaptureResult:
    return CaptureResult(
        capture_id="c",
        is_parrot=is_parrot,
        probability=probability,
        call_count=call_count,
        chirp_count=0,
        window_chirp_count=0,
        is_emergency=is_emergency,
        too_quiet=too_quiet,
    )


def test_cycle_metrics_counts_and_score_distribution() -> None:
    results = [
        result(is_parrot=True, probability=0.9, call_count=4, is_emergency=True),
        result(probability=0.1),
        result(too_quiet=True),
    ]

    values = metrics.cycle_metrics(results, elapsed_seconds=1.23456)

    assert values == {
        "CycleFailures": 0,
        "Captures": 3,
        "ParrotCaptures": 1,
        "TooQuietCaptures": 1,
        "CallCount": 4,
        "EmergencyCycles": 1,
        "CycleSeconds": 1.235,
        "ScoreMean": 0.5,
        "ScoreStdDev": 0.4,
    }


def test_score_metrics_are_omitted_when_every_capture_is_too_quiet() -> None:
    values = metrics.cycle_metrics([result(too_quiet=True)], elapsed_seconds=0.1)

    assert "ScoreMean" not in values
    assert "ScoreStdDev" not in values


def test_emit_writes_structured_log_line(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_ENV", "dev")

    metrics.emit({"CycleFailures": 1, "CycleSeconds": 2.0})

    record = json.loads(capsys.readouterr().out)
    assert record == {
        "event": "cycle_metrics",
        "env": "dev",
        "CycleFailures": 1,
        "CycleSeconds": 2.0,
    }
