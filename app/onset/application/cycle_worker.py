"""SQS cycle.analyze 요청을 분석해 cycle.analyzed 결과를 발행하는 워커."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, TypeGuard

from app.onset.application.cycle_analyzer import (
    CaptureInput,
    CaptureResult,
    CycleAnalyzer,
)
from app.onset.infra.sqs import SqsMessage

logger = logging.getLogger(__name__)

REQUEST_TYPE = "cycle.analyze"
RESULT_TYPE = "cycle.analyzed"
RECEIVE_RETRY_SECONDS = 5.0


class Queue(Protocol):
    async def receive(
        self, queue_url: str, *, wait_seconds: int
    ) -> list[SqsMessage]: ...

    async def delete(self, queue_url: str, receipt_handle: str) -> None: ...

    async def change_visibility(
        self, queue_url: str, receipt_handle: str, timeout_seconds: int
    ) -> None: ...

    async def send(self, queue_url: str, body: Mapping[str, Any]) -> None: ...


class InvalidMessageError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CycleRequest:
    session_id: str
    cycle: int
    sounds: tuple[CaptureInput, ...]


def parse_request(body: str) -> CycleRequest:
    try:
        data = json.loads(body)
    except (ValueError, RecursionError) as e:
        raise InvalidMessageError(f"JSON 파싱 실패: {e!r}") from e
    if not isinstance(data, dict):
        raise InvalidMessageError("본문이 객체가 아님")
    if data.get("type") != REQUEST_TYPE:
        raise InvalidMessageError(f"지원하지 않는 type: {data.get('type')!r}")

    session_id = data.get("session_id")
    cycle = data.get("cycle")
    sounds = data.get("sounds")
    if not _is_text(session_id):
        raise InvalidMessageError("session_id가 빈 값이거나 문자열이 아님")
    # bool은 int의 하위 타입이라 따로 거른다.
    if not isinstance(cycle, int) or isinstance(cycle, bool):
        raise InvalidMessageError("cycle이 정수가 아님")
    if not isinstance(sounds, list) or not sounds:
        raise InvalidMessageError("sounds가 비어 있거나 배열이 아님")
    return CycleRequest(
        session_id=session_id,
        cycle=cycle,
        sounds=tuple(_parse_sound(s) for s in sounds),
    )


def _parse_sound(raw: object) -> CaptureInput:
    if not isinstance(raw, dict):
        raise InvalidMessageError("sounds 항목이 객체가 아님")
    sound_id = raw.get("sound_id")
    object_key = raw.get("object_key")
    captured_at = raw.get("captured_at")
    if not _is_text(sound_id) or not _is_text(object_key):
        raise InvalidMessageError(
            "sound_id 또는 object_key가 빈 값이거나 문자열이 아님"
        )
    if not isinstance(captured_at, str):
        raise InvalidMessageError("captured_at이 문자열이 아님")
    try:
        at = datetime.fromisoformat(captured_at)
    except ValueError as e:
        raise InvalidMessageError(f"captured_at 형식 오류: {captured_at!r}") from e
    if at.tzinfo is None:
        raise InvalidMessageError("captured_at에 시간대가 없음")
    return CaptureInput(capture_id=sound_id, s3_key=object_key, captured_at=at)


def _is_text(value: object) -> TypeGuard[str]:
    return isinstance(value, str) and bool(value)


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
        "sounds": [
            {
                "sound_id": r.capture_id,
                "is_parrot": r.is_parrot,
                "score": r.probability,
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
        model_version: str,
        wait_seconds: int = 20,
        heartbeat_seconds: float = 60.0,
        visibility_timeout_seconds: int = 300,
    ) -> None:
        self._queue = queue
        self._analyzer = analyzer
        self._request_url = request_queue_url
        self._result_url = result_queue_url
        self._model_version = model_version
        self._wait_seconds = wait_seconds
        self._heartbeat_seconds = heartbeat_seconds
        self._visibility_timeout = visibility_timeout_seconds
        self._stopping = asyncio.Event()

    def stop(self) -> None:
        """새 메시지 수신을 멈춘다. 처리 중인 사이클은 끝까지 처리한다."""
        self._stopping.set()

    async def run(self) -> None:
        logger.info("SQS cycle worker started: %s", self._request_url)
        while not self._stopping.is_set():
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
        """성공하면 결과를 발행하고 요청을 삭제한다. 실패하면 요청을 남겨 재시도와 DLQ에 맡긴다."""
        try:
            request = parse_request(message.body)
        except InvalidMessageError:
            logger.exception("잘못된 요청 메시지 %s", message.message_id)
            return False

        started = time.monotonic()
        heartbeat = asyncio.create_task(self._keep_invisible(message.receipt_handle))
        try:
            results = await self._analyzer.analyze(
                request.sounds, tolerate_failures=False
            )
            await self._queue.send(
                self._result_url,
                build_result(request, results, self._model_version),
            )
            await self._queue.delete(self._request_url, message.receipt_handle)
        except asyncio.CancelledError:
            # 종료로 중단된 요청은 가시성 만료를 기다리지 않고 바로 큐에 돌려놓는다.
            await self._release(message.receipt_handle)
            raise
        except Exception:
            logger.exception(
                "사이클 분석 실패 session=%s cycle=%d",
                request.session_id,
                request.cycle,
            )
            return False
        finally:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat

        logger.info(
            "사이클 분석 완료 session=%s cycle=%d sounds=%d elapsed=%.1fs",
            request.session_id,
            request.cycle,
            len(request.sounds),
            time.monotonic() - started,
        )
        return True

    async def _release(self, receipt_handle: str) -> None:
        try:
            await self._queue.change_visibility(self._request_url, receipt_handle, 0)
        except Exception:
            logger.exception("요청 반환 실패")

    async def _keep_invisible(self, receipt_handle: str) -> None:
        while True:
            await asyncio.sleep(self._heartbeat_seconds)
            try:
                await self._queue.change_visibility(
                    self._request_url, receipt_handle, self._visibility_timeout
                )
            except Exception:
                logger.exception("가시성 연장 실패")
