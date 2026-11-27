import sys

import boto3
import sentry_sdk
from sentry_sdk.utils import event_from_exception

from app import config, sentry


def test_storage_secret_key_is_scrubbed_from_failed_client_creation() -> None:
    sentry.init()
    options = sentry_sdk.get_client().options

    try:
        boto3.client(
            "s3",
            endpoint_url="invalid",
            aws_access_key_id=config.STORAGE_ACCESS_KEY,
            aws_secret_access_key=config.STORAGE_SECRET_KEY,
        )
    except ValueError:
        event, _ = event_from_exception(sys.exc_info(), client_options=options)

    frames = [frame["vars"] for frame in event["exception"]["values"][0]["stacktrace"]["frames"]]
    assert config.STORAGE_SECRET_KEY in str(frames)

    options["event_scrubber"].scrub_event(event)

    assert config.STORAGE_SECRET_KEY not in str(frames)
