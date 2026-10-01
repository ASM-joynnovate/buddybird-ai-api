"""SQS cycle.analyze 요청을 분석해 cycle.analyzed 결과를 발행하는 워커."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from app import metrics
from app.health import HealthState
from app.onset.application.cycle_analyzer import (
    CaptureInput,
    CaptureResult,
    CycleAnalyzer,
)
from app.onset.infra.sqs import SqsMessage

logger = logging.getLogger(__name__)

RESULT_TYPE = "cycle.analyzed"
RECEIVE_RETRY_SECONDS = 5.0
# 원본 본문과 합쳐 SQS 메시지 한도(256KB)를 넘지 않도록 실패 이유를 자른다.
DEAD_LETTER_REASON_MAX_CHARS = 1000


class Queue(Protocol):
    async def receive(
        self, queue_url: str, *, wait_seconds: int
    ) -> list[SqsMessage]: ...

    async def delete(self, queue_url: str, receipt_handle: str) -> None: ...

    async def change_visibility(
        self, queue_url: str, receipt_handle: str, timeout_seconds: int
    ) -> None: ...

    async def send(self, queue_url: str, body: Mapping[str, Any]) -> None: ...

    async def send_raw(
        self, queue_url: str, body: str, attributes: Mapping[str, str]
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class CycleRequest:
    session_id: str
    cycle: int
    sounds: tuple[CaptureInput, ...]


def parse_request(body: str) -> CycleRequest:
    """buddybird-api가 보낸 값을 그대로 믿고 읽는다. 값이 없거나 형식이 다르면 예외가 난다."""
    data = json.loads(body)
    return CycleRequest(
        session_id=data["session_id"],
        cycle=data["cycle"],
        sounds=tuple(
            CaptureInput(
                capture_id=s["sound_id"],
                s3_key=s["object_key"],
                captured_at=datetime.fromisoformat(s["captured_at"]),
            )
            for s in data["sounds"]
        ),
    )


def build_result(
    request: CycleRequest, results: list[CaptureResult], model_version: str
) -> dict[str, Any]:
    return {
        "type": RESULT_TYPE,
        "session_id": request.session_id,
        "cycle": request.cycle,
        "model_version": model_version,
        "analyzed_at": datetime.now(UTC).isoformat(),
        "is_emergency": any(r.is_emergency for r in results),
        "call_count": sum(r.call_count for r in results),
        "sounds": [
            {
                "sound_id": r.capture_id,
                "is_parrot": r.is_parrot,
                "score": r.probability,
                "call_count": r.call_count,
                "chirp_count": r.chirp_count,
                "window_chirp_count": r.window_chirp_count,
                "is_emergency": r.is_emergency,
            }
            for r in results
        ],
    }


class CycleWorker:
    def __init__(
        self,
        queue: Queue,
        analyzer: CycleAnalyzer,
        *,
        request_queue_url: str,
        result_queue_url: str,
        dead_letter_queue_url: str,
        model_version: str,
        wait_seconds: int = 20,
        health: HealthState | None = None,
    ) -> None:
        self._health = health or HealthState()
        self._queue = queue
        self._analyzer = analyzer
        self._request_url = request_queue_url
        self._result_url = result_queue_url
        self._dead_letter_url = dead_letter_queue_url
        self._model_version = model_version
        self._wait_seconds = wait_seconds
        self._stopping = asyncio.Event()

    def stop(self) -> None:
        """새 메시지 수신을 멈춘다. 처리 중인 사이클은 끝까지 처리한다."""
        self._stopping.set()

    async def run(self) -> None:
        logger.info("SQS cycle worker started: %s", self._request_url)
        while not self._stopping.is_set():
            self._health.waiting()
            try:
                messages = await self._queue.receive(
                    self._request_url, wait_seconds=self._wait_seconds
                )
            except Exception:
                logger.exception("SQS 수신 실패")
                await asyncio.sleep(RECEIVE_RETRY_SECONDS)
                continue
            for message in messages:
                if self._stopping.is_set():
                    await self._release(message.receipt_handle)
                    continue
                try:
                    await self.handle(message)
                except Exception:
                    logger.exception("메시지 %s 처리 중 예외", message.message_id)
        logger.info("SQS cycle worker stopped")

    async def handle(self, message: SqsMessage) -> bool:
        """성공하면 결과를 발행하고 요청을 삭제한다.

        요청을 읽거나 분석하거나 결과를 발행하다 실패하면 재시도하지 않고 요청을 바로 DLQ로 옮긴다.
        결과를 발행한 뒤의 요청 삭제 실패는 처리 실패로 보지 않는다.
        """
        self._health.processing()
        started = time.monotonic()
        try:
            request = parse_request(message.body)
            results = await self._analyzer.analyze(request.sounds)
            await self._queue.send(
                self._result_url,
                build_result(request, results, self._model_version),
            )
        except asyncio.CancelledError:
            # 종료로 중단된 요청은 가시성 만료를 기다리지 않고 바로 큐에 돌려놓는다.
            await self._release(message.receipt_handle)
            raise
        except Exception as e:
            logger.exception("요청 %s 처리 실패", message.message_id)
            metrics.emit(metrics.failure_metrics())
            await self._dead_letter(message, repr(e))
            return False

        try:
            await self._queue.delete(self._request_url, message.receipt_handle)
        except Exception:
            # 결과는 이미 발행됐다. 요청이 다시 보이면 같은 결과를 한 번 더 발행하고,
            # buddybird-api가 session_id, cycle, model_version으로 중복을 거른다.
            logger.exception("요청 %s 삭제 실패", message.message_id)

        elapsed = time.monotonic() - started
        logger.info(
            "사이클 분석 완료 session=%s cycle=%d sounds=%d elapsed=%.1fs",
            request.session_id,
            request.cycle,
            len(request.sounds),
            elapsed,
        )
        metrics.emit(metrics.cycle_metrics(results, elapsed))
        return True

    async def _dead_letter(self, message: SqsMessage, reason: str) -> None:
        # DLQ 전송이 실패하면 요청을 남겨 SQS 재수신과 redrive policy에 맡긴다.
        try:
            await self._queue.send_raw(
                self._dead_letter_url,
                message.body,
                {"error": reason[:DEAD_LETTER_REASON_MAX_CHARS]},
            )
            await self._queue.delete(self._request_url, message.receipt_handle)
        except asyncio.CancelledError:
            await self._release(message.receipt_handle)
            raise
        except Exception:
            logger.exception("요청 %s DLQ 이동 실패", message.message_id)

    async def _release(self, receipt_handle: str) -> None:
        try:
            await self._queue.change_visibility(self._request_url, receipt_handle, 0)
        except Exception:
            logger.exception("요청 반환 실패")
