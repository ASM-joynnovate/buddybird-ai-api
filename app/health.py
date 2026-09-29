"""워커 헬스 상태 기록과 ECS 컨테이너 헬스체크 명령.

워커는 HealthState로 상태를 파일에 남기고, ECS는 `python -m app.health`로 판정한다.
정상이면 0, 비정상이면 1로 종료한다.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Literal

DEFAULT_PATH = Path(tempfile.gettempdir()) / "buddybird-ai-api-health.json"
# long polling 20초와 수신 실패 재시도 5초에 여유를 둔 값
IDLE_LIMIT_SECONDS = 90.0
# 현재 추정 최대 사이클 처리 시간(약 16초)에 넉넉한 여유를 둔 값
PROCESSING_LIMIT_SECONDS = 600.0
MAX_INFERENCE_FAILURES = 3

Phase = Literal["starting", "idle", "processing"]


@dataclass(frozen=True, slots=True)
class HealthSnapshot:
    model_ready: bool = False
    phase: Phase = "starting"
    # time.monotonic() 값. Linux와 macOS의 monotonic 시계는 프로세스 사이에서 공유된다.
    phase_since: float = 0.0
    inference_failures: int = 0


def evaluate(snapshot: HealthSnapshot, now: float) -> str | None:
    """비정상이면 이유를, 정상이면 None을 돌려준다."""
    if not snapshot.model_ready:
        return "모델 준비 전"
    elapsed = now - snapshot.phase_since
    if snapshot.phase == "idle" and elapsed > IDLE_LIMIT_SECONDS:
        return f"SQS 조회가 {elapsed:.0f}초째 멈춤"
    if snapshot.phase == "processing" and elapsed > PROCESSING_LIMIT_SECONDS:
        return f"사이클 처리가 {elapsed:.0f}초째 끝나지 않음"
    if snapshot.inference_failures >= MAX_INFERENCE_FAILURES:
        return f"추론 연속 {snapshot.inference_failures}회 실패"
    return None


class HealthState:
    """워커 상태를 기록한다. path가 None이면 파일에 쓰지 않는다."""

    def __init__(
        self,
        path: Path | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._path = path
        self._clock = clock
        self.snapshot = HealthSnapshot(phase_since=clock())
        self._write()

    def model_ready(self) -> None:
        self._set(replace(self.snapshot, model_ready=True))

    def waiting(self) -> None:
        self._set(replace(self.snapshot, phase="idle", phase_since=self._clock()))

    def processing(self) -> None:
        self._set(replace(self.snapshot, phase="processing", phase_since=self._clock()))

    def inference_succeeded(self) -> None:
        if self.snapshot.inference_failures:
            self._set(replace(self.snapshot, inference_failures=0))

    def inference_failed(self) -> None:
        failures = self.snapshot.inference_failures + 1
        self._set(replace(self.snapshot, inference_failures=failures))

    def _set(self, snapshot: HealthSnapshot) -> None:
        self.snapshot = snapshot
        self._write()

    def _write(self) -> None:
        if self._path is None:
            return
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self.snapshot)))
        tmp.replace(self._path)


def read_snapshot(path: Path) -> HealthSnapshot:
    return HealthSnapshot(**json.loads(path.read_text()))


def check(path: Path, now: float) -> str | None:
    try:
        snapshot = read_snapshot(path)
    except (OSError, ValueError, TypeError) as e:
        return f"상태 파일을 읽을 수 없음: {e!r}"
    return evaluate(snapshot, now)


def health_path() -> Path:
    return Path(os.getenv("HEALTH_FILE") or DEFAULT_PATH)


def main() -> int:
    reason = check(health_path(), time.monotonic())
    if reason is None:
        return 0
    print(f"unhealthy: {reason}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
