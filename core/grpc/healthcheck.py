"""gRPC 헬스체크 명령. SERVING이면 0, 그 외에는 1로 종료한다.

사용법:
    python -m core.grpc.healthcheck
    python -m core.grpc.healthcheck --target 127.0.0.1:50051
"""

import argparse
import asyncio
import sys

import grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc

from core.grpc.config import grpc_port

DEFAULT_TIMEOUT_SECONDS = 3.0


async def check(
    target: str,
    *,
    service: str = "",
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    async with grpc.aio.insecure_channel(target) as channel:
        stub = health_pb2_grpc.HealthStub(channel)
        response = await stub.Check(
            health_pb2.HealthCheckRequest(service=service), timeout=timeout_seconds
        )
    name: str = health_pb2.HealthCheckResponse.ServingStatus.Name(response.status)
    return name


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="gRPC 헬스체크")
    parser.add_argument("--target", default=f"127.0.0.1:{grpc_port()}")
    parser.add_argument("--service", default="")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    args = parser.parse_args(argv)

    try:
        status = asyncio.run(
            check(args.target, service=args.service, timeout_seconds=args.timeout)
        )
    except grpc.aio.AioRpcError as exc:
        print(f"{exc.code().name}: {exc.details()}", file=sys.stderr)
        return 1

    print(status)
    return 0 if status == "SERVING" else 1


if __name__ == "__main__":
    sys.exit(main())
