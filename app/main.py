import asyncio
import logging
import os
import signal

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

from app.onset.application.cycle_analyzer import CycleAnalyzer
from app.onset.application.cycle_worker import CycleWorker
from app.onset.application.session_servicer import OnsetServicer
from app.onset.infra.parrot_gate import ParrotGate
from app.onset.infra.sqs import SqsClient
from buddybird.ai.v1 import onset_pb2_grpc
from core.grpc.config import grpc_port
from core.grpc.interceptor import ErrorInterceptor

logger = logging.getLogger(__name__)

GRPC_HOST = "0.0.0.0"  # noqa: S104
SHUTDOWN_GRACE_SECONDS = 10.0
# ECS 기본 종료 대기 30초 안에 끝나도록, 수신 대기 20초가 끝날 여유만 둔다.
WORKER_STOP_SECONDS = 25.0


def create_server(
    health_servicer: health.aio.HealthServicer,
    onset_servicer: OnsetServicer | None = None,
) -> grpc.aio.Server:
    server = grpc.aio.server(interceptors=[ErrorInterceptor()])
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    if onset_servicer is not None:
        onset_pb2_grpc.add_OnsetServiceServicer_to_server(onset_servicer, server)
    return server


def create_worker(analyzer: CycleAnalyzer, model_version: str) -> CycleWorker | None:
    request_queue_url = os.getenv("SQS_PARROT_SOUND_DETECTION_QUEUE_URL")
    if not request_queue_url:
        return None
    return CycleWorker(
        SqsClient(endpoint_url=os.getenv("SQS_ENDPOINT_URL") or None),
        analyzer,
        request_queue_url=request_queue_url,
        result_queue_url=os.environ["SQS_JUDGMENT_RESULT_QUEUE_URL"],
        model_version=model_version,
    )


async def stop_worker(worker: CycleWorker, task: asyncio.Task[None]) -> None:
    worker.stop()
    try:
        await asyncio.wait_for(task, WORKER_STOP_SECONDS)
    except TimeoutError:
        logger.warning("SQS 워커가 %.0f초 안에 끝나지 않아 중단함", WORKER_STOP_SECONDS)
    except Exception:
        logger.exception("SQS 워커 비정상 종료")


async def serve(port: int) -> None:
    gate = ParrotGate()
    analyzer = CycleAnalyzer(gate)
    worker = create_worker(analyzer, gate.model_version)

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, gate.preload)

    health_servicer = health.aio.HealthServicer()
    onset_servicer = OnsetServicer(analyzer)
    server = create_server(health_servicer, onset_servicer)
    server.add_insecure_port(f"{GRPC_HOST}:{port}")
    await server.start()
    await health_servicer.set(
        health.OVERALL_HEALTH, health_pb2.HealthCheckResponse.SERVING
    )
    logger.info("gRPC server started on port %d", port)

    worker_task = asyncio.create_task(worker.run()) if worker else None

    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()

    logger.info("gRPC server shutting down")
    await health_servicer.enter_graceful_shutdown()
    if worker is not None and worker_task is not None:
        await asyncio.gather(
            stop_worker(worker, worker_task), server.stop(SHUTDOWN_GRACE_SECONDS)
        )
    else:
        await server.stop(SHUTDOWN_GRACE_SECONDS)


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    asyncio.run(serve(grpc_port()))


if __name__ == "__main__":
    main()
