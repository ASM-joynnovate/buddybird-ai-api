"""사이클 분석 지표를 구조화 로그(JSON 한 줄)로 남긴다.

CloudWatch 사용자 지정 지표 비용 없이, 필요할 때 CloudWatch Logs Insights로 조회한다.
예: fields ParrotCaptures, Captures, ScoreStdDev | filter event = "cycle_metrics"
"""

from __future__ import annotations

import json
import statistics
import sys
from collections.abc import Sequence

from app.alert import app_env
from app.onset.application.cycle_analyzer import CaptureResult

EVENT = "cycle_metrics"


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


def emit(metrics: dict[str, float]) -> None:
    record = {"event": EVENT, "env": app_env(), **metrics}
    sys.stdout.write(json.dumps(record, ensure_ascii=False) + "\n")
    sys.stdout.flush()
