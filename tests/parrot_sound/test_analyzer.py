import pytest

from app.parrot_sound import analyzer as parrot_sound_analyzer
from tests.parrot_sound.fakes import FakeGate


def test_call_count_includes_calls_outside_chirp_band() -> None:
    result = parrot_sound_analyzer.analyze(FakeGate(), "s1", "k/mixed")

    assert (result.call_count, result.chirp_count) == (5, 3)


def test_call_and_chirp_counts_split_breath_gaps() -> None:
    result = parrot_sound_analyzer.analyze(FakeGate(), "s1", "k/breath")

    assert (result.call_count, result.chirp_count) == (3, 3)


@pytest.mark.parametrize(
    ("key", "expected"), [("k/seven-30ms", 1), ("k/seven-40ms", 7)]
)
def test_emergency_chirp_count_uses_30ms_gap(key: str, expected: int) -> None:
    result = parrot_sound_analyzer.analyze(FakeGate(), "s1", key)

    assert (result.call_count, result.chirp_count) == (expected, expected)


def test_loud_sound_judged_not_parrot_counts_no_calls() -> None:
    result = parrot_sound_analyzer.analyze(FakeGate(is_parrot=False), "s1", "k/four")

    assert (result.is_parrot, result.call_count, result.chirp_count) == (False, 0, 0)


def test_too_quiet_sound_skips_gate() -> None:
    gate = FakeGate()

    results = [
        parrot_sound_analyzer.analyze(gate, "s1", "k/quiet"),
        parrot_sound_analyzer.analyze(gate, "s2", "k/four"),
    ]

    assert gate.calls == 1
    assert [(r.is_parrot, r.score, r.call_count, r.chirp_count) for r in results] == [
        (False, 0.0, 0, 0),
        (True, 0.9, 4, 4),
    ]
