import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from app.onset.domain.entities import Call, OnsetAnalysis
from app.onset.domain.exceptions import InvalidOnsetCriteriaError


@dataclass(frozen=True, slots=True, kw_only=True)
class EmergencyCriteria:
    """위급 판정 기준. 기본값은 0912 자료 측정으로 정한 값이다."""

    band_low_hz: float = 4600.0
    band_high_hz: float = 8000.0
    min_consecutive_chirps: int = 7
    peak_search_low_hz: float = 250.0
    fft_size: int = 1024
    fft_hop_samples: int = 160

    def __post_init__(self) -> None:
        invalid: dict[str, float | int] = {}
        if not 0 < self.band_low_hz < self.band_high_hz:
            invalid["band_low_hz"] = self.band_low_hz
            invalid["band_high_hz"] = self.band_high_hz
        if not 0 < self.peak_search_low_hz <= self.band_low_hz:
            invalid["peak_search_low_hz"] = self.peak_search_low_hz
        if self.min_consecutive_chirps < 1:
            invalid["min_consecutive_chirps"] = self.min_consecutive_chirps
        if self.fft_size < 2:
            invalid["fft_size"] = self.fft_size
        if self.fft_hop_samples < 1:
            invalid["fft_hop_samples"] = self.fft_hop_samples
        if invalid:
            raise InvalidOnsetCriteriaError(detail=invalid)


@dataclass(frozen=True, slots=True, kw_only=True)
class Chirp:
    """울음 하나와 그 대표 음높이."""

    call: Call
    peak_hz: float
    in_band: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class EmergencyJudgement:
    """캡처 1개의 위급 판정 결과."""

    criteria: EmergencyCriteria
    chirps: tuple[Chirp, ...]
    consecutive_chirps: int
    consecutive_seconds: float

    @property
    def in_band_chirps(self) -> tuple[Chirp, ...]:
        return tuple(chirp for chirp in self.chirps if chirp.in_band)

    @property
    def is_emergency(self) -> bool:
        return self.consecutive_chirps >= self.criteria.min_consecutive_chirps


class EmergencyAnalyzer:
    """음역대 안 울음이 연속으로 몇 번 이어졌는지로 위급을 판정한다.

    울음 검출은 OnsetAnalyzer가 맡고, 이 단계는 울음마다 대표 음높이를 구한다.
    대표 음높이는 울음 구간 전체의 파워 스펙트럼에서 가장 큰 주파수다.
    음역대 밖 울음은 횟수에서 제외하되 연속을 끊지 않는다.
    """

    def __init__(self, *, criteria: EmergencyCriteria | None = None) -> None:
        self.criteria = criteria or EmergencyCriteria()
        self._window = np.hanning(self.criteria.fft_size)

    def judge(
        self, *, analysis: OnsetAnalysis, samples: NDArray[np.float64]
    ) -> EmergencyJudgement:
        signal = np.asarray(samples, dtype=np.float64)
        chirps = tuple(
            self._to_chirp(call=call, signal=signal) for call in analysis.calls
        )
        in_band = [chirp for chirp in chirps if chirp.in_band]
        seconds = (
            in_band[-1].call.offset_seconds - in_band[0].call.onset_seconds
            if in_band
            else 0.0
        )
        return EmergencyJudgement(
            criteria=self.criteria,
            chirps=chirps,
            consecutive_chirps=len(in_band),
            consecutive_seconds=seconds,
        )

    def _to_chirp(self, *, call: Call, signal: NDArray[np.float64]) -> Chirp:
        peak_hz = self.peak_frequency(
            segment=signal[call.start_sample : call.end_sample],
            sample_rate=call.sample_rate,
        )
        return Chirp(
            call=call,
            peak_hz=peak_hz,
            in_band=self.criteria.band_low_hz <= peak_hz <= self.criteria.band_high_hz,
        )

    def peak_frequency(
        self, *, segment: NDArray[np.float64], sample_rate: int
    ) -> float:
        size = self.criteria.fft_size
        if segment.size < size:
            segment = np.pad(segment, (0, size - segment.size))
        hop = self.criteria.fft_hop_samples
        starts = np.arange(0, segment.size - size + 1, hop)
        frames = segment[starts[:, None] + np.arange(size)[None, :]] * self._window
        power = (np.abs(np.fft.rfft(frames, axis=1)) ** 2).sum(axis=0)
        freqs = np.fft.rfftfreq(size, 1 / sample_rate)
        band = (freqs >= self.criteria.peak_search_low_hz) & (
            freqs <= self.criteria.band_high_hz
        )
        if not band.any() or not math.isfinite(power.sum()):
            return 0.0
        return float(freqs[band][np.argmax(power[band])])
