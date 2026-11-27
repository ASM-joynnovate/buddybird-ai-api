import logging
import math
from datetime import UTC, datetime
from typing import Any

import sentry_sdk

from app import display_score, server
from app.mimic_judgment.config import MODEL_VERSION
from app.mimic_judgment.judgment import judge, load_model

logger = logging.getLogger(__name__)

_model = load_model()


def judge_mimic(body: dict[str, Any]) -> dict[str, Any]:
    target = body["target"]
    reference = body["reference"]

    result = judge(
        _model,
        target_object_key=target["object_key"],
        word_name=reference["word_name"],
        reference_object_keys=reference["object_keys"],
    )

    judgment = {
        "status": result.status,
        "is_success": result.is_success,
        "score": None if math.isnan(result.percentile) else display_score.mimic(result.percentile),
        "n_own": result.n_own,
        "n_fill": result.n_fill,
        "set_size": result.set_size,
    }
    attributes = {"audio_id": target["audio_id"], "word_id": reference["word_id"], **judgment}

    sentry_sdk.update_current_span(attributes=attributes)
    logger.info(
        "모사 판정 결과; audio_id=%(audio_id)s word_id=%(word_id)s status=%(status)s is_success=%(is_success)s"
        " score=%(score)s n_own=%(n_own)s n_fill=%(n_fill)s set_size=%(set_size)s",
        attributes,
    )

    return {
        "type": "audio.mimic_judged",
        "session_id": body["session_id"],
        "model_version": MODEL_VERSION,
        "analyzed_at": datetime.now(UTC).isoformat(),
        "target": {"audio_id": target["audio_id"]},
        "reference": {"word_id": reference["word_id"]},
        "judgment": judgment,
    }


if __name__ == "__main__":
    server.serve(judge_mimic, name="모사 판정")
