import json
import os
from typing import Any

import pytest

os.environ.update(
    AWS_DEFAULT_REGION="ap-northeast-2",
    S3_BUCKET="bucket",
    SQS_JUDGMENT_RESULT_QUEUE_URL="http://sqs/result",
    MIMIC_JUDGMENT_MODEL_VERSION="parrot-mimicry-judgment@v1.0.1",
    PARROT_DETECTION_MODEL_VERSION="parrot-sound-gate@v2.0.1",
)


class FakeSqs:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def send_message(self, **params: Any) -> None:
        assert params["QueueUrl"] == os.environ["SQS_JUDGMENT_RESULT_QUEUE_URL"]

        self.sent.append(json.loads(params["MessageBody"]))


@pytest.fixture(autouse=True)
def fake_s3(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.mimic_judgment import judgment
    from app.parrot_detection import detection
    from tests.mimic_judgment.fakes import FakeMimicJudgmentS3
    from tests.parrot_detection.fakes import FakeParrotDetectionS3

    monkeypatch.setattr(detection, "_s3", FakeParrotDetectionS3())
    monkeypatch.setattr(judgment, "_s3", FakeMimicJudgmentS3())


@pytest.fixture
def results(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    from app import sqs

    fake_sqs = FakeSqs()

    monkeypatch.setattr(sqs, "_sqs", fake_sqs)

    return fake_sqs.sent
