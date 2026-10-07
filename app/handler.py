import asyncio
import json
import logging
import os
import time
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import boto3

from app import metrics
from app.parrot_gate import ParrotGate
from app.sound_analyzer import SoundResult, analyze

logger = logging.getLogger(__name__)
logging.getLogger().setLevel(os.getenv("LOG_LEVEL", "INFO"))

_pyproject = tomllib.loads(
    (Path(__file__).parent.parent / "pyproject.toml").read_text()
)
_result_queue_url = os.environ["SQS_JUDGMENT_RESULT_QUEUE_URL"]

_gate = ParrotGate()
_sqs = boto3.client("sqs", endpoint_url=os.getenv("SQS_ENDPOINT_URL") or None)


async def process_record(
    record: dict[str, Any], semaphore: asyncio.Semaphore
) -> SoundResult:
    body = json.loads(record["body"])
    [sound] = body["data"]

    async with semaphore:
        sound_result = await asyncio.to_thread(
            analyze, _gate, sound["audio_id"], sound["object_key"]
        )

    result_message = {
        "type": "audio.parrot_detected",
        "session_id": body["session_id"],
        "analyzer_version": f"{_pyproject['project']['name']}@{_pyproject['project']['version']}",
        "analyzed_at": datetime.now(UTC).isoformat(),
        "data": [
            {
                "audio_id": sound["audio_id"],
                "is_parrot": sound_result.is_parrot,
                "score": sound_result.score,
                "call_count": sound_result.call_count,
                "chirp_count": sound_result.chirp_count,
            }
        ],
    }
    await asyncio.to_thread(
        _sqs.send_message,
        QueueUrl=_result_queue_url,
        MessageBody=json.dumps(result_message, ensure_ascii=False),
    )

    return sound_result


async def process_batch(records: list[dict[str, Any]]) -> dict[str, Any]:
    started = time.monotonic()
    semaphore = asyncio.Semaphore(4)
    outcomes = await asyncio.gather(
        *(process_record(record, semaphore) for record in records),
        return_exceptions=True,
    )

    sound_results = []
    batch_item_failures = []
    for record, outcome in zip(records, outcomes, strict=True):
        if isinstance(outcome, BaseException):
            logger.error(
                "요청 처리 실패; message_id=%s", record["messageId"], exc_info=outcome
            )
            batch_item_failures.append({"itemIdentifier": record["messageId"]})
        else:
            sound_results.append(outcome)

    metrics.emit(sound_results, len(batch_item_failures), time.monotonic() - started)

    return {"batchItemFailures": batch_item_failures}


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    return asyncio.run(process_batch(event["Records"]))
