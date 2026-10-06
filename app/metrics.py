import json
import os
import statistics
from collections.abc import Sequence

from app.sound_analyzer import SoundResult


def emit(results: Sequence[SoundResult], failures: int, elapsed_seconds: float) -> None:
    record: dict[str, object] = {
        "event": "batch_metrics",
        "env": os.getenv("APP_ENV") or "local",
        "FailedSounds": failures,
        "Sounds": len(results),
        "ParrotSounds": sum(result.is_parrot for result in results),
        "TooQuietSounds": sum(result.too_quiet for result in results),
        "CallCount": sum(result.call_count for result in results),
        "BatchSeconds": round(elapsed_seconds, 3),
    }

    scores = [result.score for result in results if not result.too_quiet]
    if scores:
        record["ScoreMean"] = round(statistics.fmean(scores), 4)
        record["ScoreStdDev"] = round(statistics.pstdev(scores), 4)

    print(json.dumps(record, ensure_ascii=False), flush=True)
