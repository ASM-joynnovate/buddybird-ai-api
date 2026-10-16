import io

import numpy as np
import soundfile

from app.parrot_sound.gate import ParrotGate

SAMPLE_RATE = 16000


def chirps(
    count: int, frequency: float = 5000.0, silence_seconds: float = 0.15
) -> np.ndarray:
    silence = np.zeros(int(silence_seconds * SAMPLE_RATE))
    times = np.arange(int(0.12 * SAMPLE_RATE)) / SAMPLE_RATE
    parts = [silence]
    for _ in range(count):
        parts.extend([0.5 * np.sin(2 * np.pi * frequency * times), silence])
    return np.concatenate(parts).astype(np.float32)


SOUNDS = {
    "k/four": chirps(4),
    "k/silent": np.zeros(SAMPLE_RATE, dtype=np.float32),
    "k/mixed": np.concatenate([chirps(3), chirps(2, frequency=2000.0)]),
    "k/quiet": (chirps(4) * 0.001).astype(np.float32),
    "k/breath": chirps(3, silence_seconds=0.06),
    "k/seven-30ms": chirps(7, silence_seconds=0.03),
    "k/seven-40ms": chirps(7, silence_seconds=0.04),
}


class FakeS3:
    def get_object(self, **params: str) -> dict[str, io.BytesIO]:
        body = io.BytesIO()
        soundfile.write(
            body, SOUNDS[params["Key"]], SAMPLE_RATE, format="WAV", subtype="FLOAT"
        )
        body.seek(0)
        return {"Body": body}


class FakeGate(ParrotGate):
    def __init__(self, *, is_parrot: bool = True) -> None:
        self.is_parrot = is_parrot
        self.calls = 0

    def predict(self, audio: np.ndarray, sample_rate: int) -> tuple[float, bool]:
        self.calls += 1
        return (0.9 if self.is_parrot else 0.2), self.is_parrot
