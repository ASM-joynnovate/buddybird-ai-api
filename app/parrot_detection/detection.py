import io
import logging
from dataclasses import dataclass

import boto3
import numpy as np
import soundfile

from app import config
from app.parrot_detection.calls import count_chirps, detect_calls
from app.parrot_detection.loudness import is_too_quiet, maxwin_db
from app.parrot_detection.model import ParrotDetectionModel

logger = logging.getLogger(__name__)

_s3 = boto3.client("s3")


@dataclass(frozen=True, slots=True, kw_only=True)
class ParrotDetection:
    is_parrot: bool
    score: float
    call_count: int
    chirp_count: int


def detect(model: ParrotDetectionModel, audio_id: str, object_key: str) -> ParrotDetection:
    s3_object = _s3.get_object(Bucket=config.S3_BUCKET, Key=object_key)
    audio, sample_rate = soundfile.read(io.BytesIO(s3_object["Body"].read()), dtype="float32")

    if audio.ndim == 2:
        audio = audio.mean(axis=1)

    loudness = maxwin_db(audio, sample_rate)
    too_quiet = is_too_quiet(loudness)

    logger.info("음량 측정; audio_id=%s maxwin_db=%.2f too_quiet=%s", audio_id, loudness, too_quiet)

    if too_quiet:
        return ParrotDetection(is_parrot=False, score=0.0, call_count=0, chirp_count=0)

    score, is_parrot = model.predict(audio, sample_rate)

    call_count = 0
    chirp_count = 0

    if is_parrot:
        audio = audio.astype(np.float64)
        calls = detect_calls(audio, sample_rate)

        call_count = len(calls)
        chirp_count = count_chirps(audio, sample_rate, calls)

    return ParrotDetection(is_parrot=is_parrot, score=score, call_count=call_count, chirp_count=chirp_count)
