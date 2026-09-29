"""운영 알림을 Slack 수신 웹훅으로 보낸다.

웹훅 주소(`ALERT_SLACK_WEBHOOK_URL`)가 없으면 보내지 않고 로그만 남긴다. 전송 실패는 워커를 멈추지 않는다.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import urllib.request
from collections.abc import Callable, Mapping

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 5.0
MAX_FIELD_LENGTH = 500

Post = Callable[[str, bytes], None]


def app_env() -> str:
    return os.getenv("APP_ENV") or "local"


def _post(url: str, body: bytes) -> None:
    request = urllib.request.Request(  # noqa: S310
        url, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS):  # noqa: S310
        pass


def slack_payload(title: str, fields: Mapping[str, str]) -> dict[str, object]:
    blocks: list[dict[str, object]] = [
        {"type": "header", "text": {"type": "plain_text", "text": title[:150]}}
    ]
    if fields:
        blocks.append(
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*{name}*\n{value[:MAX_FIELD_LENGTH]}"}
                    for name, value in fields.items()
                ],
            }
        )
    return {"text": title, "blocks": blocks}


class SlackAlerts:
    def __init__(
        self,
        webhook_url: str | None,
        *,
        environment: str,
        post: Post = _post,
    ) -> None:
        self._url = webhook_url
        self._post = post
        self.environment = environment
        self._pending: set[asyncio.Future[None]] = set()

    @classmethod
    def from_env(cls) -> SlackAlerts:
        return cls(os.getenv("ALERT_SLACK_WEBHOOK_URL") or None, environment=app_env())

    def send(self, title: str, fields: Mapping[str, str] | None = None) -> None:
        """바로 보낸다. 이벤트 루프 밖(시작 실패 처리 등)에서 쓴다."""
        full = {
            "환경": self.environment,
            "호스트": socket.gethostname(),
            **(fields or {}),
        }
        logger.warning("alert: %s %s", title, full)
        if self._url is None:
            return
        try:
            self._post(self._url, json.dumps(slack_payload(title, full)).encode())
        except Exception:
            logger.exception("Slack 알림 전송 실패: %s", title)

    def send_later(self, title: str, fields: Mapping[str, str] | None = None) -> None:
        """이벤트 루프를 막지 않도록 스레드에서 보낸다."""
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(None, self.send, title, dict(fields or {}))
        self._pending.add(future)
        future.add_done_callback(self._pending.discard)
