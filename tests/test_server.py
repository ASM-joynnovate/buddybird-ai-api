import asyncio
import socket
import sys
from collections.abc import AsyncIterator
from typing import Any

import grpc
import pytest
from google.rpc import error_details_pb2
from grpc_health.v1 import health, health_pb2
from grpc_status import rpc_status

from app.main import create_server
from app.onset.domain.exceptions import InvalidAudioSignalError
from core.common.errors import ResourceNotFoundError
from core.grpc import healthcheck
from core.grpc.interceptor import (
    ERROR_DOMAIN,
    INTERNAL_ERROR_CODE,
    INTERNAL_ERROR_MESSAGE,
    to_status_code,
)

TEST_SERVICE = "test.Errors"


def _identity(value: bytes) -> bytes:
    return value


async def _raise_not_found(_: bytes, __: Any) -> bytes:
    raise ResourceNotFoundError


async def _raise_invalid_audio(_: bytes, __: Any) -> bytes:
    raise InvalidAudioSignalError(detail={"sample_rate": 0})


async def _raise_unhandled(_: bytes, __: Any) -> bytes:
    raise RuntimeError("secret internal detail")


async def _stream_then_not_found(_: bytes, __: Any) -> AsyncIterator[bytes]:
    yield b"first"
    raise ResourceNotFoundError


def _test_handler() -> grpc.GenericRpcHandler:
    serializers: dict[str, Any] = {
        "request_deserializer": _identity,
        "response_serializer": _identity,
    }
    return grpc.method_handlers_generic_handler(
        TEST_SERVICE,
        {
            "NotFound": grpc.unary_unary_rpc_method_handler(
                _raise_not_found, **serializers
            ),
            "InvalidAudio": grpc.unary_unary_rpc_method_handler(
                _raise_invalid_audio, **serializers
            ),
            "Unhandled": grpc.unary_unary_rpc_method_handler(
                _raise_unhandled, **serializers
            ),
            "StreamNotFound": grpc.unary_stream_rpc_method_handler(
                _stream_then_not_found, **serializers
            ),
        },
    )


@pytest.fixture
async def target() -> AsyncIterator[str]:
    health_servicer = health.aio.HealthServicer()
    server = create_server(health_servicer)
    server.add_generic_rpc_handlers((_test_handler(),))
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    await health_servicer.set(
        health.OVERALL_HEALTH, health_pb2.HealthCheckResponse.SERVING
    )
    yield f"127.0.0.1:{port}"
    await server.stop(None)


async def _call_unary(target: str, method: str) -> grpc.aio.AioRpcError:
    async with grpc.aio.insecure_channel(target) as channel:
        rpc = channel.unary_unary(
            f"/{TEST_SERVICE}/{method}",
            request_serializer=_identity,
            response_deserializer=_identity,
        )
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await rpc(b"")
    return exc_info.value


def _error_info(error: grpc.aio.AioRpcError) -> error_details_pb2.ErrorInfo:
    status = rpc_status.from_call(error)
    assert status is not None
    info = error_details_pb2.ErrorInfo()
    assert status.details[0].Unpack(info)
    return info


def _unused_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
    return port


async def test_health_check_returns_serving(target: str) -> None:
    assert await healthcheck.check(target) == "SERVING"


async def test_healthcheck_command_exits_zero_when_serving(target: str) -> None:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "core.grpc.healthcheck",
        "--target",
        target,
        stdout=asyncio.subprocess.PIPE,
    )
    stdout, _ = await process.communicate()
    assert process.returncode == 0
    assert stdout.decode().strip() == "SERVING"


def test_healthcheck_command_exits_one_when_server_is_down() -> None:
    target = f"127.0.0.1:{_unused_port()}"
    assert healthcheck.main(["--target", target, "--timeout", "1"]) == 1


async def test_custom_error_returns_status_code_and_error_info(target: str) -> None:
    error = await _call_unary(target, "NotFound")

    assert error.code() == grpc.StatusCode.NOT_FOUND
    assert error.details() == "요청한 리소스를 찾을 수 없습니다."
    info = _error_info(error)
    assert info.reason == "COMMON__RESOURCE_NOT_FOUND"
    assert info.domain == ERROR_DOMAIN


async def test_domain_error_hides_detail(target: str) -> None:
    error = await _call_unary(target, "InvalidAudio")

    assert error.code() == grpc.StatusCode.INVALID_ARGUMENT
    info = _error_info(error)
    assert info.reason == "ONSET__INVALID_AUDIO_SIGNAL"
    assert not info.metadata
    assert "sample_rate" not in (error.details() or "")


async def test_unhandled_error_returns_internal_without_exception_message(
    target: str,
) -> None:
    error = await _call_unary(target, "Unhandled")

    assert error.code() == grpc.StatusCode.INTERNAL
    assert error.details() == INTERNAL_ERROR_MESSAGE
    assert _error_info(error).reason == INTERNAL_ERROR_CODE


async def test_stream_error_returns_status_after_sent_messages(target: str) -> None:
    async with grpc.aio.insecure_channel(target) as channel:
        rpc = channel.unary_stream(
            f"/{TEST_SERVICE}/StreamNotFound",
            request_serializer=_identity,
            response_deserializer=_identity,
        )
        received: list[bytes] = []

        async def consume() -> None:
            async for message in rpc(b""):
                received.append(message)

        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await consume()

    assert received == [b"first"]
    assert exc_info.value.code() == grpc.StatusCode.NOT_FOUND
    assert _error_info(exc_info.value).reason == "COMMON__RESOURCE_NOT_FOUND"


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (400, grpc.StatusCode.INVALID_ARGUMENT),
        (404, grpc.StatusCode.NOT_FOUND),
        (422, grpc.StatusCode.INVALID_ARGUMENT),
        (500, grpc.StatusCode.INTERNAL),
        (409, grpc.StatusCode.INVALID_ARGUMENT),
        (503, grpc.StatusCode.INTERNAL),
    ],
)
def test_to_status_code(code: int, expected: grpc.StatusCode) -> None:
    assert to_status_code(code) == expected
