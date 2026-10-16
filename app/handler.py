import asyncio
import json
import logging
import os
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import boto3
import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration

from app.parrot_sound import analyzer as parrot_sound_analyzer
from app.parrot_sound.gate import ParrotGate

logger = logging.getLogger(__name__)
logging.getLogger().setLevel(os.getenv("LOG_LEVEL", "INFO"))

_pyproject = tomllib.loads(
    (Path(__file__).parent.parent / "pyproject.toml").read_text()
)
_analyzer_version = (
    f"{_pyproject['project']['name']}@{_pyproject['project']['version']}"
)
_result_queue_url = os.environ["SQS_JUDGMENT_RESULT_QUEUE_URL"]

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    environment=os.getenv("APP_ENV") or "local",
    release=_analyzer_version,
    traces_sample_rate=1.0,
    integrations=[LoggingIntegration(capture_sentry_logs=True)],
)

_gate = ParrotGate()
_sqs = boto3.client("sqs", endpoint_url=os.getenv("SQS_ENDPOINT_URL") or None)


async def process_record(record: dict[str, Any], semaphore: asyncio.Semaphore) -> None:
    headers = {
        key: value["stringValue"]
        for key, value in record.get("messageAttributes", {}).items()
    }

    with sentry_sdk.isolation_scope():
        transaction = sentry_sdk.continue_trace(
            headers, op="queue.process", name="process_record"
        )

        with sentry_sdk.start_transaction(transaction):
            try:
                body = json.loads(record["body"])
                [sound] = body["data"]

                async with semaphore:
                    sound_result = await asyncio.to_thread(
                        parrot_sound_analyzer.analyze,
                        _gate,
                        sound["audio_id"],
                        sound["object_key"],
                    )

                result = {
                    "audio_id": sound["audio_id"],
                    "is_parrot": sound_result.is_parrot,
                    "score": sound_result.score,
                    "call_count": sound_result.call_count,
                    "chirp_count": sound_result.chirp_count,
                }
                sentry_sdk.update_current_span(attributes=result)
                logger.info(
                    "판정 결과; audio_id=%(audio_id)s is_parrot=%(is_parrot)s"
                    " score=%(score).4f call_count=%(call_count)s"
                    " chirp_count=%(chirp_count)s",
                    result,
                )

                result_message = {
                    "type": "audio.parrot_detected",
                    "session_id": body["session_id"],
                    "analyzer_version": _analyzer_version,
                    "analyzed_at": datetime.now(UTC).isoformat(),
                    "data": [result],
                }
                trace_headers = {
                    "sentry-trace": sentry_sdk.get_traceparent(),
                    "baggage": sentry_sdk.get_baggage(),
                }
                await asyncio.to_thread(
                    _sqs.send_message,
                    QueueUrl=_result_queue_url,
                    MessageBody=json.dumps(result_message, ensure_ascii=False),
                    MessageAttributes={
                        key: {"DataType": "String", "StringValue": value}
                        for key, value in trace_headers.items()
                        if value
                    },
                )
            except Exception:
                logger.exception("요청 처리 실패; message_id=%s", record["messageId"])
                raise


async def process_batch(records: list[dict[str, Any]]) -> dict[str, Any]:
    semaphore = asyncio.Semaphore(4)
    outcomes = await asyncio.gather(
        *(process_record(record, semaphore) for record in records),
        return_exceptions=True,
    )

    return {
        "batchItemFailures": [
            {"itemIdentifier": record["messageId"]}
            for record, outcome in zip(records, outcomes, strict=True)
            if isinstance(outcome, BaseException)
        ]
    }


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    try:
        return asyncio.run(process_batch(event["Records"]))
    finally:
        # Lambda 정지 전 Sentry 전송
        sentry_sdk.flush()
