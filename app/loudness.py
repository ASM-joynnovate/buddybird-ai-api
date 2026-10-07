import numpy as np
from numpy.typing import ArrayLike

TOO_QUIET_DBFS = -39.0


def maxwin_db(audio: ArrayLike, sample_rate: int) -> float:
    """100 ms window RMS 최댓값의 dBFS"""
    audio = np.asarray(audio, dtype=np.float64)
    window_samples = max(1, round(sample_rate * 100.0 / 1000.0))

    if audio.size == 0:
        rms = 0.0
    elif audio.size <= window_samples:
        rms = float(np.sqrt(np.mean(audio**2)))
    else:
        rms = max(
            float(np.sqrt(np.mean(audio[start : start + window_samples] ** 2)))
            for start in range(0, audio.size - window_samples + 1, window_samples)
        )

    return 20.0 * float(np.log10(rms + 1e-12))


def is_too_quiet(dbfs: float) -> bool:
    return dbfs < TOO_QUIET_DBFS
