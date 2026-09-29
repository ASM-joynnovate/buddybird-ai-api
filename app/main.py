import asyncio
import logging
import os
import signal
from collections.abc import Callable

from app.alert import SlackAlerts
from app.health import HealthState, health_path
from app.onset.application.cycle_analyzer import CycleAnalyzer
from app.onset.application.cycle_worker import CycleWorker
from app.onset.infra.parrot_gate import ParrotGate
from app.onset.infra.sqs import SqsClient

logger = logging.getLogger(__name__)

# ECS 기본 종료 대기 30초 안에 끝나도록, 수신 대기 20초가 끝날 여유만 둔다.
WORKER_STOP_SECONDS = 25.0


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"환경 변수 {name}가 비어 있음")
    return value


def create_worker(
    analyzer: CycleAnalyzer, model_version: str, health: HealthState
) -> CycleWorker:
    request_queue_url = required_env("SQS_PARROT_SOUND_DETECTION_QUEUE_URL")
    result_queue_url = required_env("SQS_JUDGMENT_RESULT_QUEUE_URL")
    return CycleWorker(
        SqsClient(endpoint_url=os.getenv("SQS_ENDPOINT_URL") or None),
        analyzer,
        request_queue_url=request_queue_url,
        result_queue_url=result_queue_url,
        model_version=model_version,
        health=health,
    )


async def stop_worker(worker: CycleWorker, task: asyncio.Task[None]) -> None:
    worker.stop()
    try:
        await asyncio.wait_for(task, WORKER_STOP_SECONDS)
    except TimeoutError:
        logger.warning("SQS 워커가 %.0f초 안에 끝나지 않아 중단함", WORKER_STOP_SECONDS)
    except Exception:
        logger.exception("SQS 워커 비정상 종료")


def inference_alert(alerts: SlackAlerts) -> Callable[[bool, int], None]:
    def notify(unhealthy: bool, failures: int) -> None:
        if unhealthy:
            alerts.send_later("ai-api 추론 연속 실패", {"연속 실패": f"{failures}회"})
        else:
            alerts.send_later("ai-api 추론 복구", {"직전 연속 실패": f"{failures}회"})

    return notify


async def serve(health: HealthState, alerts: SlackAlerts) -> None:
    gate = ParrotGate()
    analyzer = CycleAnalyzer(gate, health=health)
    worker = create_worker(analyzer, gate.model_version, health)

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, gate.preload)
    health.model_ready()
    if alerts.environment == "prod":
        alerts.send_later("ai-api 시작", {"모델": gate.model_version})

    worker_task = asyncio.create_task(worker.run())
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    stop_task = asyncio.create_task(stop.wait())
    await asyncio.wait({worker_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)

    if worker_task.done():
        stop_task.cancel()
        # 워커가 스스로 끝나면 프로세스를 종료해 ECS가 task를 다시 띄우게 한다.
        worker_task.result()
        raise RuntimeError("SQS 워커가 예기치 않게 종료됨")
    logger.info("shutting down")
    await stop_worker(worker, worker_task)


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    alerts = SlackAlerts.from_env()
    health = HealthState(health_path(), on_inference_change=inference_alert(alerts))
    try:
        asyncio.run(serve(health, alerts))
    except Exception as e:
        title = (
            "ai-api 비정상 종료" if health.snapshot.model_ready else "ai-api 시작 실패"
        )
        alerts.send(title, {"오류": f"{type(e).__name__}: {e}"})
        raise


if __name__ == "__main__":
    main()
