import asyncio
import json
import logging
import os
import tomllib
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import boto3
import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration

from app.mimic import analyzer as mimic_analyzer
from app.mimic.judgment import MODEL_VERSION, MimicJudgment
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
_mimic = MimicJudgment()
_sqs = boto3.client("sqs", endpoint_url=os.getenv("SQS_ENDPOINT_URL") or None)


async def detect_parrot(
    body: dict[str, Any], semaphore: asyncio.Semaphore
) -> dict[str, Any]:
    [sound] = body["data"]

    async with semaphore:
        sound_result = await asyncio.to_thread(
            parrot_sound_analyzer.analyze, _gate, sound["audio_id"], sound["object_key"]
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

    return {
        "type": "audio.parrot_detected",
        "session_id": body["session_id"],
        "analyzer_version": _analyzer_version,
        "analyzed_at": datetime.now(UTC).isoformat(),
        "data": [result],
    }


async def judge_mimic(
    body: dict[str, Any], semaphore: asyncio.Semaphore
) -> dict[str, Any]:
    [sound] = body["data"]

    async with semaphore:
        word_judgments = await asyncio.to_thread(
            mimic_analyzer.analyze,
            _mimic,
            account_id=body["account_id"],
            species=body["species"],
            object_key=sound["object_key"],
            words=sound["words"],
        )

    judgments = [
        {"word_id": word["word_id"], **asdict(word_judgment)}
        for word, word_judgment in zip(sound["words"], word_judgments, strict=True)
    ]
    for judgment in judgments:
        logger.info(
            "모사 판정 결과; audio_id=%s word_id=%s status=%s is_success=%s score=%s",
            sound["audio_id"],
            judgment["word_id"],
            judgment["status"],
            judgment["is_success"],
            judgment["score"],
        )
    sentry_sdk.update_current_span(
        attributes={
            "audio_id": sound["audio_id"],
            "word_count": len(judgments),
            "success_count": sum(judgment["is_success"] for judgment in judgments),
        }
    )

    return {
        "type": "audio.mimic_judged",
        "session_id": body["session_id"],
        "analyzer_version": _analyzer_version,
        "model_version": MODEL_VERSION,
        "analyzed_at": datetime.now(UTC).isoformat(),
        "data": [{"audio_id": sound["audio_id"], "judgments": judgments}],
    }


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
                if body.get("type") == "audio.judge_mimic":
                    result_message = await judge_mimic(body, semaphore)
                else:
                    result_message = await detect_parrot(body, semaphore)

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
        sentry_sdk.flush()
