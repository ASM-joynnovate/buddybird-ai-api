"""HuggingFace parrot-sound-gate 모델 로드 및 앵무 소리 판정."""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from onnxruntime import InferenceSession

logger = logging.getLogger(__name__)

_GATE_REPO = "buddybird-ai/parrot-sound-gate"
_GATE_FILE = "gate.joblib"
_GATE_REVISION = "v2.0.0"

_PERCH_REPO = "justinchuby/Perch-onnx"
_PERCH_FILE = "perch_v2.onnx"

_SR = 32_000
_WINDOW_S = 5.0
_HOP_S = 2.5
_TARGET_PEAK = 0.25


@dataclass(frozen=True, slots=True)
class GateResult:
    probability: float
    is_parrot: bool


@dataclass(frozen=True, slots=True)
class _Models:
    bundle: dict[str, Any]
    session: InferenceSession


class ParrotGate:
    """싱글턴으로 사용한다. warm 시작 시 preload()를 호출해 cold start 지연을 없앤다."""

    def __init__(self, revision: str = _GATE_REVISION) -> None:
        self._revision = revision
        self._models: _Models | None = None
        self._lock = threading.Lock()

    def preload(self) -> None:
        """서버 시작 시 모델을 미리 로드한다."""
        self._ensure_loaded()

    def _ensure_loaded(self) -> _Models:
        if self._models is None:
            with self._lock:
                if self._models is None:
                    self._models = self._load()
        return self._models

    def _load(self) -> _Models:
        import joblib
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download

        logger.info(
            "Loading parrot-sound-gate from HuggingFace (revision=%s)...",
            self._revision,
        )
        gate_path = hf_hub_download(_GATE_REPO, _GATE_FILE, revision=self._revision)
        bundle = joblib.load(gate_path)
        logger.info("Gate loaded (threshold=%.4f)", bundle["threshold"])

        perch_path = hf_hub_download(_PERCH_REPO, _PERCH_FILE)
        session = ort.InferenceSession(str(perch_path))
        logger.info("Perch ONNX loaded")
        return _Models(bundle=bundle, session=session)

    def predict(self, audio: np.ndarray, sr: int) -> GateResult:
        models = self._ensure_loaded()
        emb = self._embed(models.session, audio, sr)
        bundle = models.bundle
        prob = float(bundle["pipeline"].predict_proba(emb.reshape(1, -1))[0, 1])
        return GateResult(probability=prob, is_parrot=prob >= bundle["threshold"])

    async def predict_async(self, audio: np.ndarray, sr: int) -> GateResult:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.predict, audio, sr)

    def _embed(
        self, session: InferenceSession, audio: np.ndarray, sr: int
    ) -> np.ndarray:
        import librosa

        audio = np.asarray(audio, dtype=np.float32)
        if audio.ndim > 1:
            audio = audio.mean(axis=tuple(range(1, audio.ndim)))
        if sr != _SR:
            audio = librosa.resample(audio, orig_sr=sr, target_sr=_SR)
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        if peak > 0:
            audio = audio * (_TARGET_PEAK / peak)

        frames = self._frames(audio)
        input_name = session.get_inputs()[0].name
        embeddings = session.run(["embedding"], {input_name: frames})[0]
        return np.asarray(embeddings.mean(axis=0), dtype=np.float32)

    def _frames(self, audio: np.ndarray) -> np.ndarray:
        window_len = round(_WINDOW_S * _SR)
        hop_len = round(_HOP_S * _SR)
        n = audio.shape[0]
        if n <= window_len:
            out = np.zeros(window_len, dtype=np.float32)
            out[:n] = audio
            return out[None, :]
        starts = list(range(0, n - window_len + 1, hop_len))
        if starts[-1] != n - window_len:
            starts.append(n - window_len)
        return np.stack([audio[s : s + window_len] for s in starts], axis=0)
