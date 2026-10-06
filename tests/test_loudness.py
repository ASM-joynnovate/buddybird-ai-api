import numpy as np
import pytest

from app.loudness import TOO_QUIET_DBFS, is_too_quiet, maxwin_db


def reference_maxwin_db(audio: np.ndarray, sr: int) -> float:
    def rms_to_db(rms: float) -> float:
        return 20.0 * float(np.log10(rms + 1e-12))

    if audio.size == 0:
        return rms_to_db(0.0)
    win = max(1, round(sr * 100.0 / 1000.0))
    hop = max(1, round(sr * 100.0 / 1000.0))
    if audio.size <= win:
        return rms_to_db(float(np.sqrt(np.mean(audio**2))))
    best = max(
        float(np.sqrt(np.mean(audio[s : s + win] ** 2)))
        for s in range(0, audio.size - win + 1, hop)
    )
    return rms_to_db(best)


@pytest.mark.parametrize("sr", [16000, 22050, 32000, 44100, 48000])
@pytest.mark.parametrize("seconds", [0.03, 0.1, 0.35, 1.0, 5.07])
def test_matches_reference(sr: int, seconds: float) -> None:
    rng = np.random.default_rng(seed=sr + int(seconds * 100))
    audio = (rng.standard_normal(int(sr * seconds)) * 0.01).astype(np.float32)

    assert maxwin_db(audio, sr) == reference_maxwin_db(audio.astype(np.float64), sr)


def test_short_burst_in_long_silence_is_not_diluted() -> None:
    sr = 16000
    audio = np.zeros(sr * 5)
    audio[sr : sr + sr // 10] = 0.1

    assert maxwin_db(audio, sr) == pytest.approx(-20.0)


def test_audio_shorter_than_window_uses_whole_rms() -> None:
    audio = np.full(800, 0.01)

    assert maxwin_db(audio, 16000) == pytest.approx(-40.0)


def test_empty_audio_is_too_quiet() -> None:
    assert is_too_quiet(maxwin_db(np.array([]), 16000))


@pytest.mark.parametrize(
    ("db", "expected"),
    [(TOO_QUIET_DBFS, False), (-38.99, False), (-39.01, True)],
)
def test_threshold_boundary_passes(db: float, expected: bool) -> None:
    assert is_too_quiet(db) is expected
