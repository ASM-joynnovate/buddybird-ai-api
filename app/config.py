import os
import tomllib
from pathlib import Path

_pyproject = tomllib.loads((Path(__file__).parent.parent / "pyproject.toml").read_text())

RELEASE = f"{_pyproject['project']['name']}@{_pyproject['project']['version']}"
ENV = os.getenv("ENV") or "local"
LOG_LEVEL = os.getenv("LOG_LEVEL") or "INFO"
SENTRY_DSN = os.getenv("SENTRY_DSN")
S3_BUCKET = os.environ["S3_BUCKET"]
SQS_ENDPOINT_URL = os.getenv("SQS_ENDPOINT_URL") or None
SQS_JUDGMENT_RESULT_QUEUE_URL = os.environ["SQS_JUDGMENT_RESULT_QUEUE_URL"]
