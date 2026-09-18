import math
from dataclasses import dataclass, fields

from app.onset.domain.exceptions import InvalidOnsetCriteriaError


@dataclass(frozen=True, slots=True, kw_only=True)
class OnsetCriteria:
    """onset 판정 기준. 기본값은 BB-494 조사에서 승인한 값이다."""

    gate_dbfs: float = -39.0
    frame_ms: float = 10.0
    max_call_silence_ms: float = 100.0
    min_call_ms: float = 30.0
    max_repeat_gap_seconds: float = 2.0
    min_repeat_calls: int = 4
    min_repeat_span_seconds: float = 5.0

    def __post_init__(self) -> None:
        invalid = {
            field.name: getattr(self, field.name)
            for field in fields(self)
            if not math.isfinite(getattr(self, field.name))
        }
        if self.frame_ms <= 0:
            invalid["frame_ms"] = self.frame_ms
        if self.min_repeat_calls < 1:
            invalid["min_repeat_calls"] = self.min_repeat_calls
        for name in (
            "max_call_silence_ms",
            "min_call_ms",
            "max_repeat_gap_seconds",
            "min_repeat_span_seconds",
        ):
            if getattr(self, name) < 0:
                invalid[name] = getattr(self, name)
        if invalid:
            raise InvalidOnsetCriteriaError(detail=invalid)

    def frame_samples(self, sample_rate: int) -> int:
        return max(1, round(sample_rate * self.frame_ms / 1000))

    def max_call_silence_samples(self, sample_rate: int) -> int:
        return round(sample_rate * self.max_call_silence_ms / 1000)

    def min_call_samples(self, sample_rate: int) -> int:
        return round(sample_rate * self.min_call_ms / 1000)

    def max_repeat_gap_samples(self, sample_rate: int) -> int:
        return round(sample_rate * self.max_repeat_gap_seconds)

    def min_repeat_span_samples(self, sample_rate: int) -> int:
        return round(sample_rate * self.min_repeat_span_seconds)


def _rms_dbfs(energy: float, samples: int) -> float:
    if samples <= 0 or energy <= 0:
        return -math.inf
    return 10 * math.log10(energy / samples)


@dataclass(frozen=True, slots=True, kw_only=True)
class Call:
    """gate 이상 frame을 짧은 무음으로 연결한 울음 하나."""

    sample_rate: int
    start_sample: int
    end_sample: int
    active_samples: int
    active_energy: float

    @property
    def onset_seconds(self) -> float:
        return self.start_sample / self.sample_rate

    @property
    def offset_seconds(self) -> float:
        return self.end_sample / self.sample_rate

    @property
    def duration_seconds(self) -> float:
        return (self.end_sample - self.start_sample) / self.sample_rate

    @property
    def active_seconds(self) -> float:
        return self.active_samples / self.sample_rate

    @property
    def active_rms_dbfs(self) -> float:
        return _rms_dbfs(self.active_energy, self.active_samples)


@dataclass(frozen=True, slots=True, kw_only=True)
class RepeatInterval:
    """앞 울음 끝부터 다음 울음 시작까지 간격이 기준 이하로 이어진 울음."""

    calls: tuple[Call, ...]
    meets_min_calls: bool
    meets_min_span: bool

    @property
    def call_count(self) -> int:
        return len(self.calls)

    @property
    def onset_seconds(self) -> float:
        return self.calls[0].onset_seconds

    @property
    def offset_seconds(self) -> float:
        return self.calls[-1].offset_seconds

    @property
    def span_seconds(self) -> float:
        return self.offset_seconds - self.onset_seconds

    @property
    def active_seconds(self) -> float:
        return sum(call.active_seconds for call in self.calls)

    @property
    def active_rms_dbfs(self) -> float:
        return _rms_dbfs(
            sum(call.active_energy for call in self.calls),
            sum(call.active_samples for call in self.calls),
        )

    @property
    def silence_gaps_seconds(self) -> tuple[float, ...]:
        return tuple(
            current.onset_seconds - previous.offset_seconds
            for previous, current in zip(self.calls, self.calls[1:], strict=False)
        )

    @property
    def is_emergency_candidate(self) -> bool:
        return self.meets_min_calls and self.meets_min_span


@dataclass(frozen=True, slots=True, kw_only=True)
class OnsetAnalysis:
    """캡처 1개의 울음, 반복 구간, 응급 후보 판정 결과."""

    sample_rate: int
    total_samples: int
    criteria: OnsetCriteria
    calls: tuple[Call, ...]
    repeat_intervals: tuple[RepeatInterval, ...]

    @property
    def duration_seconds(self) -> float:
        return self.total_samples / self.sample_rate

    @property
    def candidate_intervals(self) -> tuple[RepeatInterval, ...]:
        return tuple(
            interval
            for interval in self.repeat_intervals
            if interval.is_emergency_candidate
        )

    @property
    def is_emergency_candidate(self) -> bool:
        return bool(self.candidate_intervals)
