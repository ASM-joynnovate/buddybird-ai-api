from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class OnsetCriteria:
    """onset 판정 기준. 기본값은 BB-494 조사에서 승인한 값이다."""

    gate_dbfs: float = -39.0
    frame_ms: float = 10.0
    max_call_silence_ms: float = 100.0
    min_call_ms: float = 30.0

    def frame_samples(self, sample_rate: int) -> int:
        return max(1, round(sample_rate * self.frame_ms / 1000))

    def max_call_silence_samples(self, sample_rate: int) -> int:
        return round(sample_rate * self.max_call_silence_ms / 1000)

    def min_call_samples(self, sample_rate: int) -> int:
        return round(sample_rate * self.min_call_ms / 1000)


@dataclass(frozen=True, slots=True, kw_only=True)
class Call:
    """gate 이상 frame을 짧은 무음으로 연결한 울음 하나."""

    sample_rate: int
    start_sample: int
    end_sample: int
    active_samples: int


@dataclass(frozen=True, slots=True, kw_only=True)
class OnsetAnalysis:
    """캡처 1개에서 검출한 울음."""

    calls: tuple[Call, ...]
