import os
import tomllib
from pathlib import Path

_pyproject = tomllib.loads((Path(__file__).parent.parent / "pyproject.toml").read_text())

RELEASE = f"{_pyproject['project']['name']}@{_pyproject['project']['version']}"
ENV = os.getenv("ENV") or "local"
LOG_LEVEL = os.getenv("LOG_LEVEL") or "INFO"
SENTRY_DSN = os.getenv("SENTRY_DSN")
STORAGE_ENDPOINT_URL = os.environ["STORAGE_ENDPOINT_URL"]
STORAGE_ACCESS_KEY = os.environ["STORAGE_ACCESS_KEY"]
STORAGE_SECRET_KEY = os.environ["STORAGE_SECRET_KEY"]
STORAGE_BUCKET_NAME = os.environ["STORAGE_BUCKET_NAME"]
