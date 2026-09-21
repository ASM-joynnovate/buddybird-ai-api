"""gRPC OnsetService.AnalyzeSession 스트리밍 RPC 구현."""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import AsyncIterator

import grpc
import numpy as np

from app.onset.domain.emergency import EmergencyAnalyzer
from app.onset.domain.services import OnsetAnalyzer
from app.onset.infra.parrot_gate import ParrotGate
from app.onset.infra.s3_audio import download_audio_async
from buddybird.ai.v1 import onset_pb2, onset_pb2_grpc

logger = logging.getLogger(__name__)

_WINDOW_SECONDS = 30.0


class _SessionState:
    """스트림 세션 동안 슬라이딩 윈도우 chirp 카운트를 유지한다."""

    def __init__(self) -> None:
        self._entries: deque[tuple[float, int]] = deque()

    def add(self, captured_at_s: float, chirp_count: int) -> None:
        self._entries.append((captured_at_s, chirp_count))
        cutoff = captured_at_s - _WINDOW_SECONDS
        while self._entries and self._entries[0][0] < cutoff:
            self._entries.popleft()

    def window_chirp_count(self) -> int:
        return sum(c for _, c in self._entries)


class OnsetServicer(onset_pb2_grpc.OnsetServiceServicer):
    def __init__(self, gate: ParrotGate) -> None:
        self._gate = gate
        self._onset = OnsetAnalyzer()
        self._emergency = EmergencyAnalyzer()

    async def AnalyzeSession(  # noqa: N802
        self,
        request_iterator: AsyncIterator[onset_pb2.AnalyzeSessionRequest],
        context: grpc.aio.ServicerContext[
            onset_pb2.AnalyzeSessionRequest, onset_pb2.AnalyzeSessionResponse
        ],
    ) -> AsyncIterator[onset_pb2.AnalyzeSessionResponse]:
        state = _SessionState()

        async for req in request_iterator:
            kind = req.WhichOneof("message")
            if kind == "start":
                logger.info("Session started: %s", req.start.session_id)
                continue
            if kind != "capture":
                continue

            cap = req.capture
            chirp_count = 0
            try:
                audio, sr = await download_audio_async(cap.s3_key)
                gate_result = await self._gate.predict_async(audio, sr)

                if gate_result.is_parrot:
                    samples = audio.astype(np.float64)
                    analysis = self._onset.analyze(samples=samples, sample_rate=sr)
                    judgement = self._emergency.judge(
                        analysis=analysis, samples=samples
                    )
                    chirp_count = len(judgement.in_band_chirps)
            except Exception:
                logger.exception("capture %s 분석 실패", cap.capture_id)

            captured_at_s = cap.captured_at.seconds + cap.captured_at.nanos / 1e9
            state.add(captured_at_s, chirp_count)
            window_count = state.window_chirp_count()

            yield onset_pb2.AnalyzeSessionResponse(
                capture_id=cap.capture_id,
                chirp_count=chirp_count,
                window_chirp_count=window_count,
                is_emergency=window_count
                >= self._emergency.criteria.min_consecutive_chirps,
            )
