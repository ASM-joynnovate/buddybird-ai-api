import logging

import joblib
import numpy as np
import onnxruntime as ort
import soxr

from app import display_score
from app.parrot_detection.config import MODEL_VERSION

logger = logging.getLogger(__name__)

_SAMPLE_RATE = 32_000


class ParrotDetectionModel:
    def __init__(self) -> None:
        self._bundle = joblib.load("/app/models/gate.joblib")
        self._session = ort.InferenceSession("/app/models/perch_embedding.onnx")
        self._threshold = display_score.parrot(self._bundle["threshold"])

        logger.info("앵무새 소리 판별 모델 로드 완료; version=%s threshold=%.4f", MODEL_VERSION, self._threshold)

    def predict(self, audio: np.ndarray, sample_rate: int) -> tuple[float, bool]:
        if sample_rate != _SAMPLE_RATE:
            # librosa.resample과 같은 길이로 맞춤
            target_length = int(np.ceil(audio.size * (float(_SAMPLE_RATE) / sample_rate)))
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

            windows = np.stack([audio[start : start + window_length] for start in window_starts], axis=0)

        embeddings = self._session.run(["embedding"], {"inputs": windows})[0]
        embedding = np.asarray(embeddings.mean(axis=0), dtype=np.float32)
        score = display_score.parrot(float(self._bundle["pipeline"].predict_proba(embedding.reshape(1, -1))[0, 1]))

        return score, score >= self._threshold
