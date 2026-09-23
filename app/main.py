import asyncio
import logging
import os
import signal

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

from app.onset.application.session_servicer import OnsetServicer
from app.onset.infra.parrot_gate import ParrotGate
from buddybird.ai.v1 import onset_pb2_grpc
from core.grpc.config import grpc_port
from core.grpc.interceptor import ErrorInterceptor

logger = logging.getLogger(__name__)

GRPC_HOST = "0.0.0.0"  # noqa: S104
SHUTDOWN_GRACE_SECONDS = 10.0


def create_server(
    health_servicer: health.aio.HealthServicer,
    onset_servicer: OnsetServicer | None = None,
) -> grpc.aio.Server:
    server = grpc.aio.server(interceptors=[ErrorInterceptor()])
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    if onset_servicer is not None:
        onset_pb2_grpc.add_OnsetServiceServicer_to_server(onset_servicer, server)
    return server


async def serve(port: int) -> None:
    gate = ParrotGate()

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, gate.preload)

    health_servicer = health.aio.HealthServicer()
    onset_servicer = OnsetServicer(gate)
    server = create_server(health_servicer, onset_servicer)
    server.add_insecure_port(f"{GRPC_HOST}:{port}")
    await server.start()
    await health_servicer.set(
        health.OVERALL_HEALTH, health_pb2.HealthCheckResponse.SERVING
    )
    logger.info("gRPC server started on port %d", port)

    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()

    logger.info("gRPC server shutting down")
    await health_servicer.enter_graceful_shutdown()
    await server.stop(SHUTDOWN_GRACE_SECONDS)


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    asyncio.run(serve(grpc_port()))


if __name__ == "__main__":
    main()
