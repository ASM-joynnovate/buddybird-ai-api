"""사이클 분석 지표를 CloudWatch Embedded Metric Format(EMF) 로그로 남긴다.

표준 출력에 JSON 한 줄을 쓰면 CloudWatch Logs가 지표로 추출한다. 별도 IAM 권한은 필요 없다.
예외 없이 틀린 값을 내는 모델 이상(앵무 판정 0%, score 고정)을 분포 알람으로 잡기 위한 값이다.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
from collections.abc import Sequence
from typing import Any

from app.onset.application.cycle_analyzer import CaptureResult

NAMESPACE = "BuddyBird/AiApi"
UNITS = {"CycleSeconds": "Seconds", "ScoreMean": "None", "ScoreStdDev": "None"}


def environment() -> str:
    return os.getenv("METRICS_ENVIRONMENT") or "local"


def cycle_metrics(
    results: Sequence[CaptureResult], elapsed_seconds: float
) -> dict[str, float]:
    scored = [r.probability for r in results if not r.too_quiet]
    metrics: dict[str, float] = {
        "CycleFailures": 0,
        "Captures": len(results),
        "ParrotCaptures": sum(r.is_parrot for r in results),
        "TooQuietCaptures": sum(r.too_quiet for r in results),
        "CallCount": sum(r.call_count for r in results),
        "EmergencyCycles": int(any(r.is_emergency for r in results)),
        "CycleSeconds": round(elapsed_seconds, 3),
    }
    if scored:
        metrics["ScoreMean"] = round(statistics.fmean(scored), 4)
        metrics["ScoreStdDev"] = round(statistics.pstdev(scored), 4)
    return metrics


def failure_metrics() -> dict[str, float]:
    return {"CycleFailures": 1}


def emf_record(metrics: dict[str, float], timestamp_ms: int) -> dict[str, Any]:
    env = environment()
    return {
        "_aws": {
            "Timestamp": timestamp_ms,
            "CloudWatchMetrics": [
                {
                    "Namespace": NAMESPACE,
                    "Dimensions": [["Environment"]],
                    "Metrics": [
                        {"Name": name, "Unit": UNITS.get(name, "Count")}
                        for name in metrics
                    ],
                }
            ],
        },
        "Environment": env,
        **metrics,
    }


def emit(metrics: dict[str, float]) -> None:
    record = emf_record(metrics, int(time.time() * 1000))
    sys.stdout.write(json.dumps(record, ensure_ascii=False) + "\n")
    sys.stdout.flush()
