import numpy as np
import pytest
from numpy.typing import NDArray

from app.calls import count_chirps, detect_calls

SAMPLE_RATE = 16000


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


def chirp_count(*chirp_hz: float) -> int:
    gap = np.zeros(int(0.15 * SAMPLE_RATE))
    times = np.arange(int(0.12 * SAMPLE_RATE)) / SAMPLE_RATE
    parts = [gap]
    for hz in chirp_hz:
        parts.extend([0.5 * np.sin(2 * np.pi * hz * times), gap])
    audio = np.concatenate(parts)
    return count_chirps(audio, SAMPLE_RATE, detect_calls(audio, SAMPLE_RATE))


@pytest.mark.parametrize("signal", [silence(1.0), np.zeros(0, dtype=np.float64)])
def test_silence_returns_no_calls(signal: NDArray[np.float64]) -> None:
    assert detect_calls(signal, SAMPLE_RATE) == []


@pytest.mark.parametrize(("call_seconds", "expected_calls"), [(0.02, 0), (0.03, 1)])
def test_call_shorter_than_min_call_is_dropped(
    call_seconds: float, expected_calls: int
) -> None:
    signal = np.concatenate([silence(0.5), tone(call_seconds), silence(0.5)])
    assert len(detect_calls(signal, SAMPLE_RATE)) == expected_calls


@pytest.mark.parametrize(("silence_seconds", "expected_calls"), [(0.1, 1), (0.11, 2)])
def test_silence_up_to_max_call_silence_is_bridged(
    silence_seconds: float, expected_calls: int
) -> None:
    signal = np.concatenate([tone(0.1), silence(silence_seconds), tone(0.1)])
    calls = detect_calls(signal, SAMPLE_RATE)
    assert len(calls) == expected_calls
    if expected_calls == 1:
        assert calls[0][1] - calls[0][0] == round(0.3 * SAMPLE_RATE)


@pytest.mark.parametrize(("silence_seconds", "expected_calls"), [(0.04, 1), (0.05, 2)])
def test_max_silence_ms_sets_bridged_silence(
    silence_seconds: float, expected_calls: int
) -> None:
    signal = np.concatenate([tone(0.1), silence(silence_seconds), tone(0.1)])
    calls = detect_calls(signal, SAMPLE_RATE, max_silence_ms=40.0)
    assert len(calls) == expected_calls


def test_call_boundaries() -> None:
    signal = np.concatenate(
        [silence(0.5), tone(0.2), silence(0.5), tone(0.3), silence(0.5)]
    )
    assert detect_calls(signal, SAMPLE_RATE) == [(8000, 11200), (19200, 24000)]


def test_partial_last_frame_uses_actual_samples() -> None:
    assert detect_calls(tone(1697 / SAMPLE_RATE), SAMPLE_RATE) == [(0, 1697)]


@pytest.mark.parametrize(("amplitude", "expected_calls"), [(0.01, 0), (0.02, 1)])
def test_frames_below_minus_39_dbfs_are_not_calls(
    amplitude: float, expected_calls: int
) -> None:
    signal = tone(0.5, amplitude=amplitude)
    assert len(detect_calls(signal, SAMPLE_RATE)) == expected_calls


@pytest.mark.parametrize(("silence_seconds", "expected_calls"), [(0.1, 1), (0.11, 2)])
def test_call_timing_scales_with_sample_rate(
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
    assert len(detect_calls(signal, rate)) == expected_calls


def test_chirps_in_band_are_counted() -> None:
    assert chirp_count(*([5000.0] * 7)) == 7


def test_chirps_below_band_are_not_counted() -> None:
    assert chirp_count(*([3000.0] * 7)) == 0


def test_chirp_outside_band_is_skipped() -> None:
    assert (
        chirp_count(5000.0, 5000.0, 5000.0, 3000.0, 5000.0, 5000.0, 5000.0, 5000.0) == 7
    )


def test_silence_has_no_chirps() -> None:
    assert chirp_count() == 0
