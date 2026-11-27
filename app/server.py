import json
import logging
import sys
import threading
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import sentry_sdk

from app import config, sentry

type Process = Callable[[dict[str, Any]], dict[str, Any]]

logger = logging.getLogger(__name__)

PORT = 8080

logging.basicConfig(level=config.LOG_LEVEL, stream=sys.stdout, format="[%(levelname)s] %(message)s")
sentry.init()

_lock = threading.Lock()


def handle(message: dict[str, Any], process: Process, name: str, message_id: str | None) -> dict[str, Any]:
    with sentry_sdk.isolation_scope():
        transaction = sentry_sdk.continue_trace(message.get("trace", {}), op="queue.process", name=process.__name__)

        with sentry_sdk.start_transaction(transaction):
            try:
                result = process(message["body"])

                trace = {
                    "sentry-trace": sentry_sdk.get_traceparent(),
                    "baggage": sentry_sdk.get_baggage(),
                }

                return {"body": result, "trace": {key: value for key, value in trace.items() if value}}
            except Exception:
                logger.exception("%s 요청 처리 실패; message_id=%s", name, message_id)
                raise


def handler(process: Process, *, name: str) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:
            self._respond(HTTPStatus.OK if self.path == "/healthz" else HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            try:
                message = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                message_id = self.headers["X-Queue-Message-Id"]

                with _lock:
                    body = json.dumps(handle(message, process, name, message_id), ensure_ascii=False).encode()
            except Exception:
                self._respond(HTTPStatus.INTERNAL_SERVER_ERROR)
            else:
                self._respond(HTTPStatus.OK, body)

        def log_message(self, format: str, *args: Any) -> None:
            pass

        def _respond(self, status: HTTPStatus, body: bytes = b"") -> None:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def serve(process: Process, *, name: str) -> None:
    ThreadingHTTPServer(("", PORT), handler(process, name=name)).serve_forever()
