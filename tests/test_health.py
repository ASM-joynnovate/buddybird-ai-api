from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from app import health
from app.health import (
    IDLE_LIMIT_SECONDS,
    MAX_INFERENCE_FAILURES,
    PROCESSING_LIMIT_SECONDS,
    HealthSnapshot,
    HealthState,
    check,
    evaluate,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def ready(**overrides: Any) -> HealthSnapshot:
    base = HealthSnapshot(model_ready=True, phase="idle", phase_since=0.0)
    return replace(base, **overrides)


def test_model_not_ready_is_unhealthy() -> None:
    assert evaluate(HealthSnapshot(), now=0.0) == "모델 준비 전"


@pytest.mark.parametrize(
    ("elapsed", "healthy"),
    [(IDLE_LIMIT_SECONDS, True), (IDLE_LIMIT_SECONDS + 1, False)],
)
def test_idle_limit(elapsed: float, healthy: bool) -> None:
    assert (evaluate(ready(phase="idle"), now=elapsed) is None) is healthy


@pytest.mark.parametrize(
    ("elapsed", "healthy"),
    [(PROCESSING_LIMIT_SECONDS, True), (PROCESSING_LIMIT_SECONDS + 1, False)],
)
def test_processing_limit(elapsed: float, healthy: bool) -> None:
    assert (evaluate(ready(phase="processing"), now=elapsed) is None) is healthy


def test_long_processing_within_limit_is_not_judged_by_idle_limit() -> None:
    snapshot = ready(phase="processing")

    assert evaluate(snapshot, now=IDLE_LIMIT_SECONDS * 2) is None


@pytest.mark.parametrize(
    ("failures", "healthy"),
    [(MAX_INFERENCE_FAILURES - 1, True), (MAX_INFERENCE_FAILURES, False)],
)
def test_inference_failure_limit(failures: int, healthy: bool) -> None:
    snapshot = ready(inference_failures=failures)

    assert (evaluate(snapshot, now=0.0) is None) is healthy


def test_success_resets_inference_failures() -> None:
    state = HealthState()
    state.inference_failed()
    state.inference_failed()

    state.inference_succeeded()

    assert state.snapshot.inference_failures == 0


def test_phase_changes_record_clock(tmp_path: Path) -> None:
    clock = FakeClock()
    path = tmp_path / "health.json"
    state = HealthState(path, clock=clock)
    state.model_ready()

    clock.now = 1010.0
    state.processing()

    assert state.snapshot.phase == "processing"
    assert state.snapshot.phase_since == 1010.0
    assert check(path, now=1020.0) is None


def test_check_reads_written_state(tmp_path: Path) -> None:
    clock = FakeClock()
    path = tmp_path / "health.json"
    state = HealthState(path, clock=clock)
    state.model_ready()
    state.waiting()

    assert check(path, now=clock.now) is None
    assert check(path, now=clock.now + IDLE_LIMIT_SECONDS + 1) is not None


def test_missing_or_broken_file_is_unhealthy(tmp_path: Path) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text("{not json")

    assert check(tmp_path / "missing.json", now=0.0) is not None
    assert check(broken, now=0.0) is not None


def test_main_exit_codes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "health.json"
    monkeypatch.setenv("HEALTH_FILE", str(path))
    state = HealthState(path)

    assert health.main() == 1

    state.model_ready()
    state.waiting()

    assert health.main() == 0
