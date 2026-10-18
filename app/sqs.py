import json
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import boto3
import sentry_sdk

from app import config

logger = logging.getLogger(__name__)

_sqs = boto3.client("sqs", endpoint_url=config.SQS_ENDPOINT_URL)


def process_record(record: dict[str, Any], process: Callable[[dict[str, Any]], dict[str, Any]], name: str) -> None:
    headers = {key: value["stringValue"] for key, value in record.get("messageAttributes", {}).items()}

    with sentry_sdk.isolation_scope():
        transaction = sentry_sdk.continue_trace(headers, op="queue.process", name=process.__name__)

        with sentry_sdk.start_transaction(transaction):
            try:
                result = process(json.loads(record["body"]))

                trace_headers = {
                    "sentry-trace": sentry_sdk.get_traceparent(),
                    "baggage": sentry_sdk.get_baggage(),
                }

                _sqs.send_message(
                    QueueUrl=config.SQS_JUDGMENT_RESULT_QUEUE_URL,
                    MessageBody=json.dumps(result, ensure_ascii=False),
                    MessageAttributes={
                        key: {"DataType": "String", "StringValue": value}
                        for key, value in trace_headers.items()
                        if value
                    },
                )
            except Exception:
                logger.exception("%s 요청 처리 실패; message_id=%s", name, record["messageId"])
                raise


def process_batch(
    records: list[dict[str, Any]],
    process: Callable[[dict[str, Any]], dict[str, Any]],
    *,
    name: str,
    max_workers: int,
) -> dict[str, Any]:
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_record, record, process, name) for record in records]

    return {
        "batchItemFailures": [
            {"itemIdentifier": record["messageId"]}
            for record, future in zip(records, futures, strict=True)
            if future.exception()
        ]
    }
