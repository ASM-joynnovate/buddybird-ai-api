import numpy as np
import pytest
from numpy.typing import NDArray

from app.onset.domain.emergency import EmergencyAnalyzer, EmergencyCriteria
from app.onset.domain.exceptions import InvalidOnsetCriteriaError
from app.onset.domain.services import OnsetAnalyzer

SAMPLE_RATE = 16000
CHIRP_SECONDS = 0.12
SILENCE_SECONDS = 0.15

onset_analyzer = OnsetAnalyzer()
emergency_analyzer = EmergencyAnalyzer()


def signal_of(*chirp_hz: float) -> NDArray[np.float64]:
    silence = np.zeros(int(SILENCE_SECONDS * SAMPLE_RATE))
    times = np.arange(int(CHIRP_SECONDS * SAMPLE_RATE)) / SAMPLE_RATE
    parts = [silence]
    for hz in chirp_hz:
        parts.extend([0.5 * np.sin(2 * np.pi * hz * times), silence])
    return np.concatenate(parts)


def judge(*chirp_hz: float) -> tuple[int, float, bool]:
    samples = signal_of(*chirp_hz)
    analysis = onset_analyzer.analyze(samples=samples, sample_rate=SAMPLE_RATE)
    judgement = emergency_analyzer.judge(analysis=analysis, samples=samples)
    return (
        judgement.consecutive_chirps,
        judgement.consecutive_seconds,
        judgement.is_emergency,
    )


def test_seven_chirps_in_band_are_emergency() -> None:
    count, seconds, is_emergency = judge(*([5000.0] * 7))

    assert count == 7
    assert seconds == pytest.approx(7 * CHIRP_SECONDS + 6 * SILENCE_SECONDS, abs=0.05)
    assert is_emergency


def test_six_chirps_in_band_are_not_emergency() -> None:
    count, _, is_emergency = judge(*([5000.0] * 6))

    assert count == 6
    assert not is_emergency


def test_chirps_below_band_are_not_counted() -> None:
    count, seconds, is_emergency = judge(*([3000.0] * 7))

    assert count == 0
    assert seconds == 0.0
    assert not is_emergency


def test_chirp_outside_band_keeps_the_sequence() -> None:
    count, _, is_emergency = judge(
        5000.0, 5000.0, 5000.0, 3000.0, 5000.0, 5000.0, 5000.0, 5000.0
    )

    assert count == 7
    assert is_emergency


def test_peak_frequency_matches_the_tone() -> None:
    samples = signal_of(5500.0)
    analysis = onset_analyzer.analyze(samples=samples, sample_rate=SAMPLE_RATE)
    judgement = emergency_analyzer.judge(analysis=analysis, samples=samples)

    assert len(judgement.chirps) == 1
    assert judgement.chirps[0].peak_hz == pytest.approx(5500.0, abs=25.0)
    assert judgement.chirps[0].in_band


def test_empty_capture_is_not_emergency() -> None:
    samples = np.zeros(SAMPLE_RATE)
    analysis = onset_analyzer.analyze(samples=samples, sample_rate=SAMPLE_RATE)
    judgement = emergency_analyzer.judge(analysis=analysis, samples=samples)

    assert judgement.chirps == ()
    assert not judgement.is_emergency


@pytest.mark.parametrize(
    "changes",
    [
        {"band_low_hz": 8000.0, "band_high_hz": 4600.0},
        {"peak_search_low_hz": 5000.0},
        {"min_consecutive_chirps": 0},
        {"fft_size": 1},
        {"fft_hop_samples": 0},
    ],
)
def test_invalid_criteria_are_rejected(changes: dict[str, float | int]) -> None:
    with pytest.raises(InvalidOnsetCriteriaError):
        EmergencyCriteria(**changes)  # type: ignore[arg-type]
