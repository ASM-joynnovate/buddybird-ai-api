import logging
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

import sentry_sdk

from app import config, sentry, sqs
from app.parrot_detection.config import MODEL_VERSION
from app.parrot_detection.detection import detect
from app.parrot_detection.model import ParrotDetectionModel

logger = logging.getLogger(__name__)

logging.getLogger().setLevel(config.LOG_LEVEL)
sentry.init()

_model = ParrotDetectionModel()


def detect_parrot(body: dict[str, Any]) -> dict[str, Any]:
    [sound] = body["data"]

    detection = detect(_model, sound["audio_id"], sound["object_key"])

    result = {"audio_id": sound["audio_id"], **asdict(detection)}

    sentry_sdk.update_current_span(attributes=result)
    logger.info(
        "앵무새 소리 판별 결과; audio_id=%(audio_id)s is_parrot=%(is_parrot)s score=%(score).4f"
        " call_count=%(call_count)s chirp_count=%(chirp_count)s",
        result,
    )

    return {
        "type": "audio.parrot_detected",
        "session_id": body["session_id"],
        "model_version": MODEL_VERSION,
        "analyzed_at": datetime.now(UTC).isoformat(),
        "data": [result],
    }


def handler(event: dict[str, Any], _context: object) -> dict[str, Any]:
    try:
        return sqs.process_batch(event["Records"], detect_parrot, name="앵무새 소리 판별", max_workers=4)
    finally:
        sentry_sdk.flush()
