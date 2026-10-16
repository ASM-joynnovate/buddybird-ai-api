import logging
from pathlib import Path

import joblib
import numpy as np
import onnxruntime as ort
import soxr

logger = logging.getLogger(__name__)

_GATE_REVISION = "v2.0.0"
_GATE_PATH = Path("/var/task/models/gate.joblib")
_PERCH_PATH = Path("/var/task/models/perch_embedding.onnx")
_SAMPLE_RATE = 32_000


class ParrotGate:
    def __init__(self) -> None:
        self._bundle = joblib.load(_GATE_PATH)
        self._session = ort.InferenceSession(_PERCH_PATH)

        logger.info(
            "판정 모델 로드 완료; revision=%s threshold=%.4f",
            _GATE_REVISION,
            self._bundle["threshold"],
        )

    def predict(self, audio: np.ndarray, sample_rate: int) -> tuple[float, bool]:
        if sample_rate != _SAMPLE_RATE:
            # librosa.resample과 같은 길이로 맞춤
            target_length = int(
                np.ceil(audio.size * (float(_SAMPLE_RATE) / sample_rate))
            )
            audio = soxr.resample(audio, sample_rate, _SAMPLE_RATE)[:target_length]
            audio = np.pad(audio, (0, target_length - audio.size))

        window_length = round(5.0 * _SAMPLE_RATE)
        hop_length = round(2.5 * _SAMPLE_RATE)
        if audio.size <= window_length:
            windows = np.pad(audio, (0, window_length - audio.size))[None, :]
        else:
            window_starts = list(range(0, audio.size - window_length + 1, hop_length))
            # 마지막 window는 소리 끝에 맞춤
            if window_starts[-1] != audio.size - window_length:
                window_starts.append(audio.size - window_length)
            windows = np.stack(
                [audio[start : start + window_length] for start in window_starts],
                axis=0,
            )

        embeddings = self._session.run(["embedding"], {"inputs": windows})[0]
        embedding = np.asarray(embeddings.mean(axis=0), dtype=np.float32)

        score = float(
            self._bundle["pipeline"].predict_proba(embedding.reshape(1, -1))[0, 1]
        )
        return score, score >= self._bundle["threshold"]


# Docker 빌드 단계에서 모델 파일 생성
if __name__ == "__main__":
    import shutil

    import onnx.utils
    from huggingface_hub import hf_hub_download

    _GATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        hf_hub_download(
            "buddybird-ai/parrot-sound-gate",
            "gate-2.0.0.joblib",
            revision=_GATE_REVISION,
        ),
        _GATE_PATH,
    )

    onnx.utils.extract_model(
        hf_hub_download(
            "justinchuby/Perch-onnx",
            "perch_v2.onnx",
            revision="da88bf8c37c0b3068fc706fe509f633b9fbd28c1",
        ),
        _PERCH_PATH,
        ["inputs"],
        ["embedding"],
        infer_shapes=False,
    )
