import json
import threading
from collections.abc import Iterator
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from typing import Any

import pytest

from app import server

TRACE_ID = "0af7651916cd43dd8448eb211c80319c"


def summarize(body: dict[str, Any]) -> dict[str, Any]:
    return {"session_id": body["session_id"]}


@pytest.fixture
def port() -> Iterator[int]:
    http_server = ThreadingHTTPServer(("127.0.0.1", 0), server.handler(summarize, name="테스트"))

    threading.Thread(target=http_server.serve_forever, daemon=True).start()

    yield http_server.server_port

    http_server.shutdown()
    http_server.server_close()


def request(port: int, method: str, path: str, message: dict[str, Any] | None = None) -> tuple[int, Any]:
    connection = HTTPConnection("127.0.0.1", port)

    connection.request(
        method,
        path,
        body=None if message is None else json.dumps(message),
        headers={"X-Queue-Message-Id": "m-1"},
    )

    response = connection.getresponse()
    payload = response.read()

    connection.close()

    return response.status, json.loads(payload) if payload else None


@pytest.mark.parametrize(("path", "status"), [("/healthz", 200), ("/", 404)])
def test_only_healthz_answers_get(port: int, path: str, status: int) -> None:
    assert request(port, "GET", path) == (status, None)


def test_request_is_not_written_to_stderr(port: int, capsys: pytest.CaptureFixture[str]) -> None:
    request(port, "GET", "/healthz")

    assert capsys.readouterr().err == ""


def test_result_is_returned_with_continued_trace(port: int) -> None:
    message = {"body": {"session_id": "session-1"}, "trace": {"sentry-trace": f"{TRACE_ID}-b7ad6b7169203331-1"}}

    status, result = request(port, "POST", "/", message)

    assert status == 200
    assert result["body"] == {"session_id": "session-1"}
    assert result["trace"]["sentry-trace"].startswith(TRACE_ID)


@pytest.mark.parametrize("message", [{"body": {}}, {"session_id": "session-1"}])
def test_failed_request_returns_500_without_result(
    port: int,
    message: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    assert request(port, "POST", "/", message) == (500, None)
    assert "테스트 요청 처리 실패; message_id=m-1" in caplog.text
