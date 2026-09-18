from __future__ import annotations

import inspect
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING, Any, NoReturn

import grpc
from google.protobuf import any_pb2
from google.rpc import error_details_pb2, status_pb2
from grpc_status import rpc_status

from core.common.errors import CustomError

logger = logging.getLogger(__name__)

ERROR_DOMAIN = "buddybird-ai-api"
INTERNAL_ERROR_CODE = "COMMON__INTERNAL_SERVER_ERROR"
INTERNAL_ERROR_MESSAGE = "서버 내부 오류가 발생했습니다. 관리자에게 문의해주세요."

_STATUS_CODES = {
    400: grpc.StatusCode.INVALID_ARGUMENT,
    404: grpc.StatusCode.NOT_FOUND,
    422: grpc.StatusCode.INVALID_ARGUMENT,
    500: grpc.StatusCode.INTERNAL,
}

# aio 서버의 behavior는 코루틴이지만 grpc 스텁은 동기 함수로 선언한다.
Behavior = Callable[..., Any]

if TYPE_CHECKING:
    MethodHandler = grpc.RpcMethodHandler[Any, Any]


def to_status_code(code: int) -> grpc.StatusCode:
    """CustomError의 HTTP 기준 code를 gRPC 상태 코드로 변환한다."""
    if code in _STATUS_CODES:
        return _STATUS_CODES[code]
    if code >= 500:
        return grpc.StatusCode.INTERNAL
    return grpc.StatusCode.INVALID_ARGUMENT


def _error_status(
    status_code: grpc.StatusCode, error_code: str, message: str
) -> grpc.Status:
    detail = any_pb2.Any()
    detail.Pack(error_details_pb2.ErrorInfo(reason=error_code, domain=ERROR_DOMAIN))
    status: grpc.Status = rpc_status.to_status(
        status_pb2.Status(code=status_code.value[0], message=message, details=[detail])
    )
    return status


async def _abort(
    context: grpc.aio.ServicerContext[Any, Any], exc: Exception
) -> NoReturn:
    if isinstance(exc, CustomError):
        status = _error_status(to_status_code(exc.code), exc.error_code, exc.message)
    else:
        logger.error(
            "exception",
            exc_info=exc,
            extra={"data": {"exception_class": exc, "message": str(exc)}},
        )
        status = _error_status(
            grpc.StatusCode.INTERNAL, INTERNAL_ERROR_CODE, INTERNAL_ERROR_MESSAGE
        )
    await context.abort_with_status(status)


def _wrap_response(behavior: Behavior) -> Behavior:
    async def wrapper(request: Any, context: grpc.aio.ServicerContext[Any, Any]) -> Any:
        try:
            return await behavior(request, context)
        except grpc.aio.AbortError:
            raise
        except Exception as exc:
            await _abort(context, exc)

    return wrapper


def _wrap_stream(behavior: Behavior) -> Behavior:
    async def wrapper(
        request: Any, context: grpc.aio.ServicerContext[Any, Any]
    ) -> AsyncIterator[Any]:
        try:
            result = behavior(request, context)
            if inspect.isasyncgen(result):
                async for response in result:
                    yield response
            else:
                await result
        except grpc.aio.AbortError:
            raise
        except Exception as exc:
            await _abort(context, exc)

    return wrapper


class ErrorInterceptor(grpc.aio.ServerInterceptor):
    """CustomError와 처리하지 않은 예외를 gRPC 상태와 ErrorInfo로 변환한다."""

    async def intercept_service(
        self,
        continuation: Callable[
            [grpc.HandlerCallDetails], Awaitable[MethodHandler | None]
        ],
        handler_call_details: grpc.HandlerCallDetails,
    ) -> MethodHandler | None:
        handler = await continuation(handler_call_details)
        if handler is None:
            return None

        serializers: dict[str, Any] = {
            "request_deserializer": handler.request_deserializer,
            "response_serializer": handler.response_serializer,
        }
        if handler.unary_unary:
            return grpc.unary_unary_rpc_method_handler(
                _wrap_response(handler.unary_unary), **serializers
            )
        if handler.unary_stream:
            return grpc.unary_stream_rpc_method_handler(
                _wrap_stream(handler.unary_stream), **serializers
            )
        if handler.stream_unary:
            return grpc.stream_unary_rpc_method_handler(
                _wrap_response(handler.stream_unary), **serializers
            )
        if handler.stream_stream:
            return grpc.stream_stream_rpc_method_handler(
                _wrap_stream(handler.stream_stream), **serializers
            )
        return handler
