from app.mimic import analyzer as mimic_analyzer
from tests.mimic.fakes import FakeMimic


def test_references_are_downloaded_per_word_keeping_suffix() -> None:
    model = FakeMimic()

    mimic_analyzer.analyze(
        model,
        account_id="user-1",
        species="macaw",
        object_key="q/sound.wav",
        words=[
            {
                "word_id": "w-1",
                "name": "안녕",
                "reference_object_keys": ["r/1.m4a", "r/2.wav"],
            },
            {"word_id": "w-2", "name": "사랑해", "reference_object_keys": []},
        ],
    )

    assert model.calls == [
        {
            "query": b"q/sound.wav",
            "words": [
                ("안녕", [(".m4a", b"r/1.m4a"), (".wav", b"r/2.wav")]),
                ("사랑해", []),
            ],
            "account_id": "user-1",
            "species": "macaw",
        }
    ]
