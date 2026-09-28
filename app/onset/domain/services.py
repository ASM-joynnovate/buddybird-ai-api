import numpy as np
from numpy.typing import NDArray

from app.onset.domain.entities import Call, OnsetAnalysis, OnsetCriteria
from app.onset.domain.exceptions import InvalidAudioSignalError


class OnsetAnalyzer:
    """캡처 1개에서 울음을 검출한다.

    samples는 full scale을 1로 정규화한 mono 신호다.
    """

    def __init__(self, *, criteria: OnsetCriteria | None = None) -> None:
        self.criteria = criteria or OnsetCriteria()

    def analyze(
        self, *, samples: NDArray[np.float64], sample_rate: int
    ) -> OnsetAnalysis:
        if sample_rate <= 0:
            raise InvalidAudioSignalError(detail={"sample_rate": sample_rate})
        signal = np.asarray(samples, dtype=np.float64)
        if signal.ndim != 1:
            raise InvalidAudioSignalError(detail={"ndim": signal.ndim})
        if not np.isfinite(signal).all():
            raise InvalidAudioSignalError(detail="non-finite sample")

        return OnsetAnalysis(
            sample_rate=sample_rate,
            calls=tuple(self._detect_calls(signal=signal, sample_rate=sample_rate)),
        )

    def _detect_calls(
        self, *, signal: NDArray[np.float64], sample_rate: int
    ) -> list[Call]:
        if signal.size == 0:
            return []
        frame_samples = self.criteria.frame_samples(sample_rate)
        starts = np.arange(0, signal.size, frame_samples)
        counts = np.minimum(frame_samples, signal.size - starts)
        sums = np.add.reduceat(signal * signal, starts)
        with np.errstate(divide="ignore"):
            rms_dbfs = 10 * np.log10(sums / counts)

        active = np.flatnonzero(rms_dbfs >= self.criteria.gate_dbfs)
        if active.size == 0:
            return []
        breaks = starts[active[1:]] - (starts[active[:-1]] + counts[active[:-1]])
        groups = np.split(
            active,
            np.flatnonzero(breaks > self.criteria.max_call_silence_samples(sample_rate))
            + 1,
        )

        min_call_samples = self.criteria.min_call_samples(sample_rate)
        calls = []
        for frame_ids in groups:
            active_samples = int(counts[frame_ids].sum())
            if active_samples < min_call_samples:
                continue
            calls.append(
                Call(
                    sample_rate=sample_rate,
                    start_sample=int(starts[frame_ids[0]]),
                    end_sample=int(starts[frame_ids[-1]] + counts[frame_ids[-1]]),
                    active_samples=active_samples,
                )
            )
        return calls
