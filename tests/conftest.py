import pytest

from app.parrot_sound import analyzer as parrot_sound_analyzer
from tests.parrot_sound.fakes import FakeS3


@pytest.fixture(autouse=True)
def fake_s3(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIO_S3_BUCKET", "bucket")
    monkeypatch.setattr(parrot_sound_analyzer, "_s3", FakeS3())
