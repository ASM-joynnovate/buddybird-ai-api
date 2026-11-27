import os

import pytest

os.environ.update(
    {
        "STORAGE_ENDPOINT_URL": "https://account.r2.cloudflarestorage.com",
        "STORAGE_ACCESS_KEY": "access-key",
        "STORAGE_SECRET_KEY": "secret-key",
        "STORAGE_BUCKET_NAME": "bucket",
        "MIMIC_JUDGMENT_MODEL_VERSION": "parrot-mimicry-judgment@v1.0.1",
        "PARROT_DETECTION_MODEL_VERSION": "parrot-sound-gate@v2.0.1",
    }
)


@pytest.fixture(autouse=True)
def fake_r2(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.mimic_judgment import judgment
    from app.parrot_detection import detection
    from tests.mimic_judgment.fakes import FakeMimicJudgmentR2
    from tests.parrot_detection.fakes import FakeParrotDetectionR2

    monkeypatch.setattr(detection, "_r2", FakeParrotDetectionR2())
    monkeypatch.setattr(judgment, "_r2", FakeMimicJudgmentR2())
