"""gRPC OnsetService.AnalyzeSession 스트리밍 RPC 구현."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import UTC

import grpc

from app.onset.application.cycle_analyzer import CaptureInput, CycleAnalyzer
from buddybird.ai.v1 import onset_pb2, onset_pb2_grpc

logger = logging.getLogger(__name__)


class OnsetServicer(onset_pb2_grpc.OnsetServiceServicer):
    def __init__(self, analyzer: CycleAnalyzer) -> None:
        self._analyzer = analyzer

    async def AnalyzeSession(  # noqa: N802
        self,
        request_iterator: AsyncIterator[onset_pb2.AnalyzeSessionRequest],
        context: grpc.aio.ServicerContext[
            onset_pb2.AnalyzeSessionRequest, onset_pb2.AnalyzeSessionResponse
        ],
    ) -> AsyncIterator[onset_pb2.AnalyzeSessionResponse]:
        captures: list[CaptureInput] = []

        async for req in request_iterator:
            kind = req.WhichOneof("message")
            if kind == "start":
                logger.info("Session started: %s", req.start.session_id)
            elif kind == "capture":
                captures.append(
                    CaptureInput(
                        capture_id=req.capture.capture_id,
                        s3_key=req.capture.s3_key,
                        captured_at=req.capture.captured_at.ToDatetime(tzinfo=UTC),
                    )
                )

        results = await self._analyzer.analyze(captures, tolerate_failures=True)
        for result in results:
            yield onset_pb2.AnalyzeSessionResponse(
                capture_id=result.capture_id,
                chirp_count=result.chirp_count,
                window_chirp_count=result.window_chirp_count,
                is_emergency=result.is_emergency,
            )
