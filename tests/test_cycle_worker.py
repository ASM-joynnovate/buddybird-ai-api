import asyncio
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import pytest

from app.health import HealthState
from app.onset.application.cycle_analyzer import CaptureInput, CycleAnalyzer
from app.onset.application.cycle_worker import (
    CycleWorker,
    InvalidMessageError,
    parse_request,
)
from app.onset.infra.parrot_gate import GateResult
from app.onset.infra.sqs import SqsMessage

SAMPLE_RATE = 16000
REQUEST_URL = "http://sqs/request"
RESULT_URL = "http://sqs/result"
MODEL_VERSION = "parrot-sound-gate@test"
T0 = datetime(2026, 9, 23, 10, 0, tzinfo=UTC)


def chirps(count: int, frequency: float = 5000.0) -> np.ndarray:
    silence = np.zeros(int(0.15 * SAMPLE_RATE))
    times = np.arange(int(0.12 * SAMPLE_RATE)) / SAMPLE_RATE
    parts = [silence]
    for _ in range(count):
        parts.extend([0.5 * np.sin(2 * np.pi * frequency * times), silence])
    return np.concatenate(parts).astype(np.float32)


class FakeGate:
    async def predict_async(self, audio: np.ndarray, sr: int) -> GateResult:
        is_parrot = bool(np.abs(audio).max() > 0)
        return GateResult(probability=0.9 if is_parrot else 0.1, is_parrot=is_parrot)


class FakeLoader:
    def __init__(self, clips: dict[str, np.ndarray], delay: float = 0.0) -> None:
        self._clips = clips
        self._delay = delay

    async def __call__(self, key: str) -> tuple[np.ndarray, int]:
        await asyncio.sleep(self._delay)
        if key not in self._clips:
            raise FileNotFoundError(key)
        return self._clips[key], SAMPLE_RATE


class FakeQueue:
    def __init__(self, inbox: list[list[SqsMessage]] | None = None) -> None:
        self.inbox = inbox or []
        self.on_receive: Callable[[], None] | None = None
        self.sent: list[Mapping[str, Any]] = []
        self.deleted: list[str] = []
        self.extended: list[str] = []
        self.released: list[str] = []

    async def receive(self, queue_url: str, *, wait_seconds: int) -> list[SqsMessage]:
        if self.on_receive is not None:
            self.on_receive()
        await asyncio.sleep(0)
        return self.inbox.pop(0) if self.inbox else []

    async def delete(self, queue_url: str, receipt_handle: str) -> None:
        self.deleted.append(receipt_handle)

    async def change_visibility(
        self, queue_url: str, receipt_handle: str, timeout_seconds: int
    ) -> None:
        if timeout_seconds == 0:
            self.released.append(receipt_handle)
        else:
            self.extended.append(receipt_handle)

    async def send(self, queue_url: str, body: Mapping[str, Any]) -> None:
        assert queue_url == RESULT_URL
        self.sent.append(body)


CLIPS = {
    "k/four-a": chirps(4),
    "k/four-b": chirps(4),
    "k/four-c": chirps(4),
    "k/silent": np.zeros(SAMPLE_RATE, dtype=np.float32),
}


def message(
    captures: list[tuple[str, str, datetime]],
    overrides: dict[str, Any] | None = None,
) -> SqsMessage:
    body: dict[str, Any] = {
        "type": "cycle.analyze",
        "session_id": "session-1",
        "cycle": 3,
        "sounds": [
            {"sound_id": sid, "object_key": key, "captured_at": at.isoformat()}
            for sid, key, at in captures
        ],
    }
    body.update(overrides or {})
    return SqsMessage(message_id="m-1", receipt_handle="r-1", body=json.dumps(body))


def worker(
    queue: FakeQueue, loader: FakeLoader, heartbeat_seconds: float = 60.0
) -> CycleWorker:
    return CycleWorker(
        queue,
        CycleAnalyzer(FakeGate(), load_audio=loader),
        request_queue_url=REQUEST_URL,
        result_queue_url=RESULT_URL,
        model_version=MODEL_VERSION,
        heartbeat_seconds=heartbeat_seconds,
    )


async def test_publishes_result_in_captured_order_and_deletes_request() -> None:
    queue = FakeQueue()
    msg = message(
        [
            ("s2", "k/four-b", T0 + timedelta(seconds=10)),
            ("s1", "k/four-a", T0),
            ("s3", "k/silent", T0 + timedelta(seconds=20)),
        ]
    )

    assert await worker(queue, FakeLoader(CLIPS)).handle(msg)

    assert queue.deleted == ["r-1"]
    [result] = queue.sent
    assert result["type"] == "cycle.analyzed"
    assert result["session_id"] == "session-1"
    assert result["cycle"] == 3
    assert result["model_version"] == MODEL_VERSION
    assert result["is_emergency"] is True
    assert [
        (s["sound_id"], s["is_parrot"], s["chirp_count"], s["window_chirp_count"])
        for s in result["sounds"]
    ] == [("s1", True, 4, 4), ("s2", True, 4, 8), ("s3", False, 0, 8)]
    assert [s["is_emergency"] for s in result["sounds"]] == [False, True, True]
    assert [s["call_count"] for s in result["sounds"]] == [4, 4, 0]
    assert result["call_count"] == 8


async def test_call_count_includes_calls_outside_emergency_band() -> None:
    mixed = np.concatenate([chirps(3), chirps(2, frequency=2000.0)])
    analyzer = CycleAnalyzer(FakeGate(), load_audio=FakeLoader({"k/mixed": mixed}))

    [result] = await analyzer.analyze(
        [CaptureInput("s1", "k/mixed", T0)], tolerate_failures=False
    )

    assert (result.call_count, result.chirp_count) == (5, 3)


class NotParrotGate:
    async def predict_async(self, audio: np.ndarray, sr: int) -> GateResult:
        return GateResult(probability=0.2, is_parrot=False)


async def test_loud_capture_judged_not_parrot_counts_no_calls() -> None:
    analyzer = CycleAnalyzer(NotParrotGate(), load_audio=FakeLoader(CLIPS))

    [result] = await analyzer.analyze(
        [CaptureInput("s1", "k/four-a", T0)], tolerate_failures=False
    )

    assert (result.is_parrot, result.call_count, result.chirp_count) == (
        False,
        0,
        0,
    )


class BrokenGate:
    async def predict_async(self, audio: np.ndarray, sr: int) -> GateResult:
        raise RuntimeError("onnx session broken")


async def test_inference_failure_is_recorded_and_success_resets() -> None:
    health = HealthState()
    broken = CycleAnalyzer(BrokenGate(), load_audio=FakeLoader(CLIPS), health=health)

    await broken.analyze(
        [CaptureInput("s1", "k/four-a", T0), CaptureInput("s2", "k/four-b", T0)],
        tolerate_failures=True,
    )

    assert health.snapshot.inference_failures == 2

    healthy = CycleAnalyzer(FakeGate(), load_audio=FakeLoader(CLIPS), health=health)
    await healthy.analyze([CaptureInput("s3", "k/four-c", T0)], tolerate_failures=False)

    assert health.snapshot.inference_failures == 0


async def test_download_failure_and_too_quiet_do_not_touch_inference_failures() -> None:
    health = HealthState()
    health.inference_failed()
    analyzer = CycleAnalyzer(FakeGate(), load_audio=FakeLoader(CLIPS), health=health)

    await analyzer.analyze(
        [CaptureInput("s1", "k/missing", T0), CaptureInput("s2", "k/silent", T0)],
        tolerate_failures=True,
    )

    assert health.snapshot.inference_failures == 1


class PhaseRecordingQueue(FakeQueue):
    def __init__(self, inbox: list[list[SqsMessage]], health: HealthState) -> None:
        super().__init__(inbox)
        self._health = health
        self.phase_at_send = ""

    async def send(self, queue_url: str, body: Mapping[str, Any]) -> None:
        self.phase_at_send = self._health.snapshot.phase
        await super().send(queue_url, body)


async def test_worker_records_idle_and_processing_phases() -> None:
    health = HealthState()
    queue = PhaseRecordingQueue([[message([("s1", "k/four-a", T0)])]], health)
    phases: list[str] = []
    cycle_worker = CycleWorker(
        queue,
        CycleAnalyzer(FakeGate(), load_audio=FakeLoader(CLIPS), health=health),
        request_queue_url=REQUEST_URL,
        result_queue_url=RESULT_URL,
        model_version=MODEL_VERSION,
        health=health,
    )

    def record_then_stop() -> None:
        phases.append(health.snapshot.phase)
        if len(phases) == 2:
            cycle_worker.stop()

    queue.on_receive = record_then_stop
    await cycle_worker.run()

    assert phases == ["idle", "idle"]
    assert queue.phase_at_send == "processing"
    assert queue.deleted == ["r-1"]


async def test_window_drops_captures_older_than_30_seconds() -> None:
    analyzer = CycleAnalyzer(FakeGate(), load_audio=FakeLoader(CLIPS))

    results = await analyzer.analyze(
        [
            CaptureInput("s1", "k/four-a", T0),
            CaptureInput("s2", "k/four-b", T0 + timedelta(seconds=40)),
            CaptureInput("s3", "k/four-c", T0 + timedelta(seconds=70)),
        ],
        tolerate_failures=False,
    )

    assert [r.window_chirp_count for r in results] == [4, 4, 8]


class SpyGate(FakeGate):
    def __init__(self) -> None:
        self.calls = 0

    async def predict_async(self, audio: np.ndarray, sr: int) -> GateResult:
        self.calls += 1
        return await super().predict_async(audio, sr)


async def test_too_quiet_capture_skips_gate() -> None:
    gate = SpyGate()
    quiet = (chirps(4) * 0.001).astype(np.float32)
    analyzer = CycleAnalyzer(gate, load_audio=FakeLoader({"k/quiet": quiet, **CLIPS}))

    results = await analyzer.analyze(
        [CaptureInput("s1", "k/quiet", T0), CaptureInput("s2", "k/four-a", T0)],
        tolerate_failures=False,
    )

    assert gate.calls == 1
    assert [
        (r.is_parrot, r.probability, r.call_count, r.chirp_count) for r in results
    ] == [
        (False, 0.0, 0, 0),
        (True, 0.9, 4, 4),
    ]


async def test_failed_capture_keeps_request_for_retry() -> None:
    queue = FakeQueue()
    msg = message([("s1", "k/four-a", T0), ("s2", "k/missing", T0)])

    assert not await worker(queue, FakeLoader(CLIPS)).handle(msg)

    assert queue.sent == []
    assert queue.deleted == []


async def test_tolerant_analysis_counts_failed_capture_as_zero() -> None:
    analyzer = CycleAnalyzer(FakeGate(), load_audio=FakeLoader(CLIPS))

    results = await analyzer.analyze(
        [CaptureInput("s1", "k/missing", T0), CaptureInput("s2", "k/four-a", T0)],
        tolerate_failures=True,
    )

    assert [(r.capture_id, r.call_count, r.chirp_count) for r in results] == [
        ("s1", 0, 0),
        ("s2", 4, 4),
    ]


@pytest.mark.parametrize(
    "overrides",
    [
        {"type": "sound.classify"},
        {"sounds": []},
        {"cycle": "three"},
        {
            "sounds": [
                {
                    "sound_id": "s1",
                    "object_key": "k",
                    "captured_at": "2026-09-23T10:00:00",
                }
            ]
        },
        {"sounds": [{"sound_id": "s1", "captured_at": "2026-09-23T10:00:00Z"}]},
        {"session_id": None},
        {"session_id": 123},
        {"cycle": True},
        {"cycle": 3.9},
        {"sounds": ["s1"]},
        {"sounds": [{"sound_id": None, "object_key": "k", "captured_at": "x"}]},
        {"sounds": [{"sound_id": "s1", "object_key": "k", "captured_at": 1}]},
    ],
)
def test_rejects_malformed_request(overrides: dict[str, Any]) -> None:
    msg = message([("s1", "k", T0)], overrides)

    with pytest.raises(InvalidMessageError):
        parse_request(msg.body)


@pytest.mark.parametrize(
    "body",
    [
        '{"type": "cycle.analyze", "session_id": "s", "cycle": 1e999, "sounds": []}',
        "[" * 100_000,
        "[]",
        "null",
    ],
)
def test_rejects_unparsable_body_without_escaping(body: str) -> None:
    with pytest.raises(InvalidMessageError):
        parse_request(body)


async def test_malformed_request_is_not_deleted() -> None:
    queue = FakeQueue()
    msg = SqsMessage(message_id="m-1", receipt_handle="r-1", body="not json")

    assert not await worker(queue, FakeLoader(CLIPS)).handle(msg)

    assert queue.sent == []
    assert queue.deleted == []


async def test_extends_visibility_while_analysis_runs() -> None:
    queue = FakeQueue()
    msg = message([("s1", "k/four-a", T0)])

    assert await worker(queue, FakeLoader(CLIPS, delay=0.05), 0.01).handle(msg)

    assert queue.extended
    assert set(queue.extended) == {"r-1"}


async def test_cancelled_analysis_returns_request_to_queue() -> None:
    queue = FakeQueue()
    msg = message([("s1", "k/four-a", T0)])
    task = asyncio.create_task(worker(queue, FakeLoader(CLIPS, delay=10)).handle(msg))
    await asyncio.sleep(0.01)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert queue.released == ["r-1"]
    assert queue.sent == []
    assert queue.deleted == []


async def test_messages_received_after_stop_are_returned_unprocessed() -> None:
    queue = FakeQueue(inbox=[[message([("s1", "k/four-a", T0)])]])
    w = worker(queue, FakeLoader(CLIPS))
    queue.on_receive = w.stop

    await asyncio.wait_for(w.run(), timeout=1)

    assert queue.released == ["r-1"]
    assert queue.sent == []


class ExplodingWorker(CycleWorker):
    async def handle(self, message: SqsMessage) -> bool:
        raise RuntimeError("boom")


async def test_unexpected_handler_error_does_not_stop_worker() -> None:
    first = SqsMessage(message_id="m-1", receipt_handle="r-1", body="{}")
    second = SqsMessage(message_id="m-2", receipt_handle="r-2", body="{}")
    queue = FakeQueue(inbox=[[first], [second]])
    w = ExplodingWorker(
        queue,
        CycleAnalyzer(FakeGate(), load_audio=FakeLoader(CLIPS)),
        request_queue_url=REQUEST_URL,
        result_queue_url=RESULT_URL,
        model_version=MODEL_VERSION,
    )
    receives = 0

    def stop_after_two() -> None:
        nonlocal receives
        receives += 1
        if receives > 2:
            w.stop()

    queue.on_receive = stop_after_two

    await asyncio.wait_for(w.run(), timeout=1)

    assert receives == 3
    assert queue.inbox == []


async def test_worker_emits_metrics_for_success_and_failure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    ok = message([("s1", "k/four-a", T0), ("s2", "k/silent", T0)])
    failed = message([("s1", "k/missing", T0)])

    assert await worker(FakeQueue(), FakeLoader(CLIPS)).handle(ok)
    assert not await worker(FakeQueue(), FakeLoader(CLIPS)).handle(failed)

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    success, failure = lines
    assert (
        success["CycleFailures"],
        success["Captures"],
        success["ParrotCaptures"],
        success["TooQuietCaptures"],
    ) == (0, 2, 1, 1)
    assert failure["CycleFailures"] == 1
