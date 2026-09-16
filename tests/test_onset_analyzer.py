import math
from collections.abc import Callable

import numpy as np
import pytest
from numpy.typing import NDArray

from app.onset.domain.entities import OnsetAnalysis, OnsetCriteria
from app.onset.domain.exceptions import (
    InvalidAudioSignalError,
    InvalidOnsetCriteriaError,
)
from app.onset.domain.services import OnsetAnalyzer

SAMPLE_RATE = 16000
TONE_RMS_DBFS = 10 * math.log10(0.005)


def tone(
    seconds: float, *, amplitude: float = 0.1, sample_rate: int = SAMPLE_RATE
) -> NDArray[np.float64]:
    n = round(seconds * sample_rate)
    return np.asarray(
        amplitude * np.sin(2 * np.pi * 1000 * np.arange(n) / sample_rate),
        dtype=np.float64,
    )


def silence(seconds: float, *, sample_rate: int = SAMPLE_RATE) -> NDArray[np.float64]:
    return np.zeros(round(seconds * sample_rate), dtype=np.float64)


def repeat(
    call_seconds: list[float], gap_seconds: float, *, sample_rate: int = SAMPLE_RATE
) -> NDArray[np.float64]:
    parts = [tone(call_seconds[0], sample_rate=sample_rate)]
    for seconds in call_seconds[1:]:
        parts.append(silence(gap_seconds, sample_rate=sample_rate))
        parts.append(tone(seconds, sample_rate=sample_rate))
    return np.concatenate(parts)


def analyze(
    signal: NDArray[np.float64],
    criteria: OnsetCriteria | None = None,
    *,
    sample_rate: int = SAMPLE_RATE,
) -> OnsetAnalysis:
    return OnsetAnalyzer(criteria=criteria).analyze(
        samples=signal, sample_rate=sample_rate
    )


def test_default_criteria_match_approved_values() -> None:
    criteria = OnsetCriteria()
    assert criteria.gate_dbfs == -39.0
    assert criteria.frame_samples(SAMPLE_RATE) == 160
    assert criteria.max_call_silence_samples(SAMPLE_RATE) == 1600
    assert criteria.min_call_samples(SAMPLE_RATE) == 480
    assert criteria.max_repeat_gap_samples(SAMPLE_RATE) == 32000
    assert criteria.min_repeat_calls == 4
    assert criteria.min_repeat_span_samples(SAMPLE_RATE) == 80000


@pytest.mark.parametrize("signal", [silence(1.0), np.zeros(0, dtype=np.float64)])
def test_silence_returns_no_calls(signal: NDArray[np.float64]) -> None:
    result = analyze(signal)
    assert result.calls == ()
    assert result.repeat_intervals == ()
    assert not result.is_emergency_candidate


@pytest.mark.parametrize(("call_seconds", "expected_calls"), [(0.02, 0), (0.03, 1)])
def test_call_shorter_than_min_call_is_dropped(
    call_seconds: float, expected_calls: int
) -> None:
    signal = np.concatenate([silence(0.5), tone(call_seconds), silence(0.5)])
    assert len(analyze(signal).calls) == expected_calls


@pytest.mark.parametrize(("silence_seconds", "expected_calls"), [(0.1, 1), (0.11, 2)])
def test_silence_up_to_max_call_silence_is_bridged(
    silence_seconds: float, expected_calls: int
) -> None:
    signal = np.concatenate([tone(0.1), silence(silence_seconds), tone(0.1)])
    calls = analyze(signal).calls
    assert len(calls) == expected_calls
    if expected_calls == 1:
        assert calls[0].active_seconds == pytest.approx(0.2)
        assert calls[0].duration_seconds == pytest.approx(0.3)


@pytest.mark.parametrize(("gap_seconds", "expected_intervals"), [(2.0, 1), (2.01, 2)])
def test_calls_within_max_repeat_gap_share_interval(
    gap_seconds: float, expected_intervals: int
) -> None:
    result = analyze(repeat([0.2, 0.2], gap_seconds))
    assert len(result.calls) == 2
    assert len(result.repeat_intervals) == expected_intervals


@pytest.mark.parametrize(
    ("last_call_seconds", "span_seconds", "expected"),
    [(0.2, 5.0, True), (0.19, 4.99, False)],
)
def test_repeat_span_boundary(
    last_call_seconds: float, span_seconds: float, expected: bool
) -> None:
    result = analyze(repeat([0.2, 0.2, 0.2, last_call_seconds], 1.4))
    [interval] = result.repeat_intervals
    assert interval.call_count == 4
    assert interval.span_seconds == pytest.approx(span_seconds)
    assert interval.meets_min_calls
    assert interval.meets_min_span is expected
    assert result.is_emergency_candidate is expected


@pytest.mark.parametrize(("call_count", "expected"), [(3, False), (4, True)])
def test_repeat_call_count_boundary(call_count: int, expected: bool) -> None:
    result = analyze(repeat([1.0] * call_count, 1.0))
    [interval] = result.repeat_intervals
    assert interval.meets_min_span
    assert interval.meets_min_calls is expected
    assert result.is_emergency_candidate is expected


def test_call_and_interval_features() -> None:
    signal = np.concatenate([silence(0.5), repeat([0.2, 0.3], 0.5), silence(0.5)])
    result = analyze(signal)

    first, second = result.calls
    assert first.onset_seconds == pytest.approx(0.5)
    assert first.offset_seconds == pytest.approx(0.7)
    assert first.duration_seconds == pytest.approx(0.2)
    assert first.active_rms_dbfs == pytest.approx(TONE_RMS_DBFS)
    assert second.onset_seconds == pytest.approx(1.2)
    assert second.offset_seconds == pytest.approx(1.5)

    [interval] = result.repeat_intervals
    assert interval.silence_gaps_seconds == pytest.approx((0.5,))
    assert interval.span_seconds == pytest.approx(1.0)
    assert interval.active_seconds == pytest.approx(0.5)
    assert interval.active_rms_dbfs == pytest.approx(TONE_RMS_DBFS)
    assert result.duration_seconds == pytest.approx(2.0)


def test_partial_last_frame_uses_actual_samples() -> None:
    [call] = analyze(tone(1697 / SAMPLE_RATE)).calls
    assert call.end_sample == call.active_samples == 1697


@pytest.mark.parametrize(
    ("criteria", "expected"),
    [
        (OnsetCriteria(), False),
        (OnsetCriteria(min_repeat_calls=3), True),
        (OnsetCriteria(min_repeat_span_seconds=5.01), False),
        (OnsetCriteria(min_repeat_calls=3, max_repeat_gap_seconds=0.99), False),
    ],
)
def test_criteria_change_changes_candidate(
    criteria: OnsetCriteria, expected: bool
) -> None:
    result = analyze(repeat([1.0] * 3, 1.0), criteria)
    assert result.is_emergency_candidate is expected


@pytest.mark.parametrize(("gate_dbfs", "expected_calls"), [(-39.0, 0), (-45.0, 1)])
def test_gate_criteria_change_changes_calls(
    gate_dbfs: float, expected_calls: int
) -> None:
    signal = tone(0.5, amplitude=0.01)
    result = analyze(signal, OnsetCriteria(gate_dbfs=gate_dbfs))
    assert len(result.calls) == expected_calls


@pytest.mark.parametrize(("silence_seconds", "expected_calls"), [(0.1, 1), (0.11, 2)])
def test_time_criteria_scale_with_sample_rate(
    silence_seconds: float, expected_calls: int
) -> None:
    rate = 48000
    signal = np.concatenate(
        [
            tone(0.1, sample_rate=rate),
            silence(silence_seconds, sample_rate=rate),
            tone(0.1, sample_rate=rate),
        ]
    )
    assert len(analyze(signal, sample_rate=rate).calls) == expected_calls


@pytest.mark.parametrize(
    ("signal", "sample_rate"),
    [
        (np.zeros((2, 2), dtype=np.float64), SAMPLE_RATE),
        (np.array([0.0, np.nan], dtype=np.float64), SAMPLE_RATE),
        (silence(0.1), 0),
    ],
)
def test_invalid_signal_raises(signal: NDArray[np.float64], sample_rate: int) -> None:
    with pytest.raises(InvalidAudioSignalError):
        analyze(signal, sample_rate=sample_rate)


@pytest.mark.parametrize(
    "build",
    [
        lambda: OnsetCriteria(frame_ms=0),
        lambda: OnsetCriteria(min_repeat_calls=0),
        lambda: OnsetCriteria(max_repeat_gap_seconds=-1),
        lambda: OnsetCriteria(gate_dbfs=math.nan),
    ],
)
def test_invalid_criteria_raises(build: Callable[[], OnsetCriteria]) -> None:
    with pytest.raises(InvalidOnsetCriteriaError):
        build()
