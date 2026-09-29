"""1단계 음량 게이트. parrot-mimicry docs/step1-loudness-gate/spec-step1-loudness-gate.md를 따른다."""

import numpy as np
from numpy.typing import ArrayLike

# BB-371에서 확정한 운영 최종값. 창 100ms 조정 후에도 유지한다.
TOO_QUIET_DBFS = -39.0
WINDOW_MS = 100.0
HOP_MS = 100.0


def _rms_to_db(rms: float) -> float:
    return 20.0 * float(np.log10(rms + 1e-12))


def maxwin_db(samples: ArrayLike, sample_rate: int) -> float:
    """100ms 창을 100ms hop으로 옮기며 구한 RMS 최댓값을 dBFS로 돌려준다.

    parrot-mimicry scripts/step2/classify_folder.py의 maxwin_db()와 같은 값을 내도록 옮겼다.
    """
    audio = np.asarray(samples, dtype=np.float64)
    if audio.size == 0:
        return _rms_to_db(0.0)
    win = max(1, round(sample_rate * WINDOW_MS / 1000.0))
    hop = max(1, round(sample_rate * HOP_MS / 1000.0))
    if audio.size <= win:
        return _rms_to_db(float(np.sqrt(np.mean(audio**2))))
    best = max(
        float(np.sqrt(np.mean(audio[s : s + win] ** 2)))
        for s in range(0, audio.size - win + 1, hop)
    )
    return _rms_to_db(best)


def is_too_quiet(db: float) -> bool:
    return db < TOO_QUIET_DBFS
