import pytest

from app.parrot_detection.detection import detect
from tests.parrot_detection.fakes import FakeParrotDetectionModel


def test_call_count_includes_calls_outside_chirp_band() -> None:
    detection = detect(FakeParrotDetectionModel(), "s1", "k/mixed")

    assert (detection.call_count, detection.chirp_count) == (5, 3)


def test_call_and_chirp_counts_split_breath_gaps() -> None:
    detection = detect(FakeParrotDetectionModel(), "s1", "k/breath")

    assert (detection.call_count, detection.chirp_count) == (3, 3)


@pytest.mark.parametrize(("key", "expected"), [("k/seven-30ms", 1), ("k/seven-40ms", 7)])
def test_emergency_chirp_count_uses_30ms_gap(key: str, expected: int) -> None:
    detection = detect(FakeParrotDetectionModel(), "s1", key)

    assert (detection.call_count, detection.chirp_count) == (expected, expected)


def test_loud_sound_judged_not_parrot_counts_no_calls() -> None:
    detection = detect(FakeParrotDetectionModel(is_parrot=False), "s1", "k/four")

    assert (detection.is_parrot, detection.call_count, detection.chirp_count) == (False, 0, 0)


def test_too_quiet_sound_skips_model() -> None:
    model = FakeParrotDetectionModel()

    detections = [detect(model, "s1", "k/quiet"), detect(model, "s2", "k/four")]

    assert model.calls == 1
    assert [(d.is_parrot, d.score, d.call_count, d.chirp_count) for d in detections] == [
        (False, 0.0, 0, 0),
        (True, 0.9, 4, 4),
    ]
