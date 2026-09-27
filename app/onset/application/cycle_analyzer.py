"""사이클 단위 캡처 분석. gRPC 서비스와 SQS 워커가 함께 사용한다."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import numpy as np

from app.onset.domain.emergency import EmergencyAnalyzer
from app.onset.domain.services import OnsetAnalyzer
from app.onset.infra.parrot_gate import GateResult
from app.onset.infra.s3_audio import download_audio_async

logger = logging.getLogger(__name__)

# 측정 전 임시값. 응급 판정의 울음 7회를 세는 시간 창이며, 0912 측정 자료에는 창 길이 근거가 없다.
WINDOW_SECONDS = 30.0
# 측정 전 임시값. 2 vCPU 태스크에서 2와 4의 사이클 처리 시간을 비교한 뒤 확정한다.
MAX_CONCURRENT_CAPTURES = 4

AudioLoader = Callable[[str], Awaitable[tuple[np.ndarray, int]]]


class Gate(Protocol):
    async def predict_async(self, audio: np.ndarray, sr: int) -> GateResult: ...


@dataclass(frozen=True, slots=True)
class CaptureInput:
    capture_id: str
    s3_key: str
    captured_at: datetime


@dataclass(frozen=True, slots=True)
class CaptureResult:
    capture_id: str
    is_parrot: bool
    probability: float
    chirp_count: int
    window_chirp_count: int
    is_emergency: bool


@dataclass(frozen=True, slots=True)
class _Scored:
    is_parrot: bool
    probability: float
    chirp_count: int


_FAILED = _Scored(is_parrot=False, probability=0.0, chirp_count=0)


class _Window:
    """captured_at 기준 최근 WINDOW_SECONDS 동안의 chirp 수를 합산한다."""

    def __init__(self) -> None:
        self._entries: deque[tuple[datetime, int]] = deque()

    def add(self, captured_at: datetime, chirp_count: int) -> int:
        self._entries.append((captured_at, chirp_count))
        while (captured_at - self._entries[0][0]).total_seconds() > WINDOW_SECONDS:
            self._entries.popleft()
        return sum(c for _, c in self._entries)


class CycleAnalyzer:
    def __init__(
        self,
        gate: Gate,
        *,
        load_audio: AudioLoader = download_audio_async,
        max_concurrency: int = MAX_CONCURRENT_CAPTURES,
    ) -> None:
        self._gate = gate
        self._load_audio = load_audio
        self._max_concurrency = max_concurrency
        self._onset = OnsetAnalyzer()
        self._emergency = EmergencyAnalyzer()

    async def analyze(
        self, captures: Sequence[CaptureInput], *, tolerate_failures: bool
    ) -> list[CaptureResult]:
        """captured_at 순으로 정렬한 결과를 돌려준다.

        tolerate_failures가 False면 캡처 하나라도 실패할 때 예외를 올린다.
        """
        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def score(cap: CaptureInput) -> _Scored:
            async with semaphore:
                try:
                    return await self._score(cap)
                except Exception:
                    if not tolerate_failures:
                        raise
                    logger.exception("capture %s 분석 실패", cap.capture_id)
                    return _FAILED

        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(score(cap)) for cap in captures]

        ordered = sorted(
            zip(captures, (t.result() for t in tasks), strict=True),
            key=lambda pair: pair[0].captured_at,
        )
        threshold = self._emergency.criteria.min_consecutive_chirps
        window = _Window()
        results = []
        for cap, scored in ordered:
            window_count = window.add(cap.captured_at, scored.chirp_count)
            results.append(
                CaptureResult(
                    capture_id=cap.capture_id,
                    is_parrot=scored.is_parrot,
                    probability=scored.probability,
                    chirp_count=scored.chirp_count,
                    window_chirp_count=window_count,
                    is_emergency=window_count >= threshold,
                )
            )
        return results

    async def _score(self, cap: CaptureInput) -> _Scored:
        audio, sr = await self._load_audio(cap.s3_key)
        gate_result = await self._gate.predict_async(audio, sr)
        chirp_count = 0
        if gate_result.is_parrot:
            chirp_count = await asyncio.to_thread(self._count_chirps, audio, sr)
        return _Scored(
            is_parrot=gate_result.is_parrot,
            probability=gate_result.probability,
            chirp_count=chirp_count,
        )

    def _count_chirps(self, audio: np.ndarray, sr: int) -> int:
        samples = audio.astype(np.float64)
        analysis = self._onset.analyze(samples=samples, sample_rate=sr)
        judgement = self._emergency.judge(analysis=analysis, samples=samples)
        return len(judgement.in_band_chirps)
