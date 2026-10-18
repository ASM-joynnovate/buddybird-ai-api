import pytest

from app.mimic import analyzer as mimic_analyzer
from app.parrot_sound import analyzer as parrot_sound_analyzer
from tests.mimic.fakes import FakeMimicS3
from tests.parrot_sound.fakes import FakeParrotSoundS3


@pytest.fixture(autouse=True)
def fake_s3(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIO_S3_BUCKET", "bucket")
    monkeypatch.setattr(parrot_sound_analyzer, "_s3", FakeParrotSoundS3())
    monkeypatch.setattr(mimic_analyzer, "_s3", FakeMimicS3())
