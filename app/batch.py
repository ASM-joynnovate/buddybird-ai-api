import logging
import os
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

logging.basicConfig(
    level=logging.getLevelName(os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# cron 시각은 각 타임존의 현지 시각이며 aws-infra 스케줄과 같은 값이다.
TIMEZONE_SCHEDULES = {
    "Asia/Seoul": {"cron": "cron(0 0 * * ? *)", "name": "한국"},
    "America/New_York": {"cron": "cron(0 0 * * ? *)", "name": "미국 동부"},
    "America/Los_Angeles": {"cron": "cron(0 0 * * ? *)", "name": "미국 서부"},
    "Europe/London": {"cron": "cron(0 0 * * ? *)", "name": "유럽"},
}


def get_users_by_timezone(timezone: str) -> list[dict[str, Any]]:
    """
    타임존별 사용자 조회.

    TODO: DB 연결 후 실제 사용자 조회
    - DB_HOST, DB_USER 환경변수 사용
    - SELECT * FROM users WHERE timezone = ?
    """
    db_host = os.getenv("DB_HOST")
    db_user = os.getenv("DB_USER")

    logger.info(f"Getting users for timezone: {timezone}")

    if not db_host:
        logger.warning("DB_HOST not set. Returning empty for testing.")
        return []

    logger.debug(f"Connecting to DB at {db_host} as {db_user}")
    return []


def analyze_user(user_id: str, user_data: dict[str, Any]) -> dict[str, Any]:
    """
    단일 사용자 분석 수행.

    TODO: 실제 분석 로직 구현
    - 음원 수집
    - 판정 모델 실행
    - 결과 저장
    """
    logger.info(f"Analyzing user: {user_id}")
    return {
        "user_id": user_id,
        "status": "pending",
        "timestamp": datetime.now().isoformat(),
    }


def batch_by_timezone(timezone: str) -> dict[str, Any]:
    """
    타임존별 배치 실행.

    Args:
        timezone: 사용자 타임존 (e.g., "Asia/Seoul")

    Returns:
        배치 실행 결과
    """
    start_time = datetime.now(ZoneInfo(timezone))
    logger.info(f"Batch started for {timezone} ({start_time})")

    users = get_users_by_timezone(timezone)
    results: list[dict[str, Any]] = []

    for user in users:
        try:
            result = analyze_user(user["id"], user)
            results.append(result)
        except Exception as e:
            logger.exception(f"Error analyzing user {user['id']}")
            results.append({"user_id": user["id"], "status": "error", "error": str(e)})

    end_time = datetime.now(ZoneInfo(timezone))
    return {
        "timezone": timezone,
        "started_at": start_time.isoformat(),
        "ended_at": end_time.isoformat(),
        "total_users": len(users),
        "results": results,
    }


def main(timezone: str = "Asia/Seoul") -> None:
    """
    배치 진입점.

    EventBridge Scheduler에서 호출:
    python -m app.batch --timezone Asia/Seoul
    """
    result = batch_by_timezone(timezone)
    logger.info(f"Batch result: {result}")
    print(result)


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    timezone = "Asia/Seoul"
    if len(sys.argv) > 1:
        timezone = sys.argv[1]

    main(timezone)
