"""boto3 SQS 클라이언트를 asyncio에서 쓰도록 감싼다."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SqsMessage:
    message_id: str
    receipt_handle: str
    body: str


class SqsClient:
    def __init__(self, endpoint_url: str | None = None) -> None:
        import boto3

        self._client = boto3.client("sqs", endpoint_url=endpoint_url)

    async def receive(self, queue_url: str, *, wait_seconds: int) -> list[SqsMessage]:
        response = await asyncio.to_thread(
            self._client.receive_message,
            QueueUrl=queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=wait_seconds,
        )
        return [
            SqsMessage(
                message_id=m["MessageId"],
                receipt_handle=m["ReceiptHandle"],
                body=m["Body"],
            )
            for m in response.get("Messages", [])
        ]

    async def delete(self, queue_url: str, receipt_handle: str) -> None:
        await asyncio.to_thread(
            self._client.delete_message,
            QueueUrl=queue_url,
            ReceiptHandle=receipt_handle,
        )

    async def change_visibility(
        self, queue_url: str, receipt_handle: str, timeout_seconds: int
    ) -> None:
        await asyncio.to_thread(
            self._client.change_message_visibility,
            QueueUrl=queue_url,
            ReceiptHandle=receipt_handle,
            VisibilityTimeout=timeout_seconds,
        )

    async def send(self, queue_url: str, body: Mapping[str, Any]) -> None:
        await asyncio.to_thread(
            self._client.send_message,
            QueueUrl=queue_url,
            MessageBody=json.dumps(body, ensure_ascii=False),
        )

    async def send_raw(
        self, queue_url: str, body: str, attributes: Mapping[str, str]
    ) -> None:
        await asyncio.to_thread(
            self._client.send_message,
            QueueUrl=queue_url,
            MessageBody=body,
            MessageAttributes={
                name: {"DataType": "String", "StringValue": value}
                for name, value in attributes.items()
            },
        )
