import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.scrubber import DEFAULT_DENYLIST, EventScrubber

from app import config


def init() -> None:
    sentry_sdk.init(
        dsn=config.SENTRY_DSN,
        environment=config.ENV,
        release=config.RELEASE,
        traces_sample_rate=1.0,
        integrations=[LoggingIntegration(capture_sentry_logs=True)],
        event_scrubber=EventScrubber(denylist=[*DEFAULT_DENYLIST, "aws_secret_access_key"], recursive=True),
    )
