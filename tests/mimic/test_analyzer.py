from app.mimic import analyzer as mimic_analyzer
from tests.mimic.fakes import FakeMimic


def test_target_and_references_are_downloaded_keeping_suffix() -> None:
    model = FakeMimic()

    mimic_analyzer.analyze(
        model,
        target_object_key="q/sound.wav",
        word_name="안녕",
        reference_object_keys=["r/1.m4a", "r/2.wav"],
    )

    assert model.calls == [
        {
            "target": b"q/sound.wav",
            "word_name": "안녕",
            "references": [(".m4a", b"r/1.m4a"), (".wav", b"r/2.wav")],
        }
    ]
