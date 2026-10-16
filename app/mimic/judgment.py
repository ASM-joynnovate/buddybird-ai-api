import logging
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MIMIC_REVISION = "b1ba78905267833282c3aceaeb9f0ec02f26f386"
_MIMIC_DIR = Path("/var/task/models/mimic")
_CONTENTVEC_DIR = Path("/var/task/models/contentvec")
MODEL_VERSION = "parrot-mimicry-judgment@v1.0.0"


@dataclass(frozen=True, slots=True, kw_only=True)
class WordJudgment:
    status: str
    is_success: bool
    score: float | None
    n_own: int
    n_fill: int
    set_size: int


class MimicJudgment:
    def __init__(self) -> None:
        sys.path.insert(0, str(_MIMIC_DIR))
        import judge

        self._judge: Any = judge
        self._bundle = judge.load_bundle(_MIMIC_DIR, verify=False)
        self._encoder = judge.ContentVecEncoder(
            repo_id=str(_CONTENTVEC_DIR),
            layer=int(self._bundle.manifest["model"]["layer"]),
            weights_filename=None,
            weights_sha256=None,
        )
        self._encoder.load()
        self._lock = threading.Lock()

        logger.info(
            "모사 판정 모델 로드 완료; revision=%s threshold=%.4f",
            _MIMIC_REVISION,
            self._bundle.threshold,
        )

    def _features(self, path: Path) -> tuple[Any, str]:
        wave = self._judge.load_audio(path)
        features = self._encoder.extract(self._judge.preprocess(wave))
        return features, self._judge.content_hash(wave)

    def judge(
        self,
        query_path: Path,
        words: list[tuple[str, list[Path]]],
        *,
        account_id: str,
        species: str | None,
    ) -> list[WordJudgment]:
        with self._lock:
            query_features, _ = self._features(query_path)

            judgments = []
            for word, reference_paths in words:
                references = [self._features(path) for path in reference_paths]
                result = self._judge.judge(
                    self._bundle,
                    query_features,
                    word,
                    [features for features, _ in references],
                    account_id=account_id,
                    species=species,
                    own_content_hashes=[content_hash for _, content_hash in references],
                ).to_dict()
                judgments.append(WordJudgment(**result))

            return judgments


if __name__ == "__main__":
    import hashlib
    import json

    from huggingface_hub import snapshot_download

    def sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()

    snapshot_download(
        "buddybird-ai/parrot-mimicry-judgment",
        revision=_MIMIC_REVISION,
        local_dir=_MIMIC_DIR,
        allow_patterns=["judge/*", "manifest.json", "*.npz", "*.npy"],
    )
    manifest = json.loads((_MIMIC_DIR / "manifest.json").read_text())
    for name, file in manifest["files"].items():
        if sha256(_MIMIC_DIR / name) != file["sha256"].removeprefix("sha256:"):
            raise ValueError(f"모사 판정 번들 해시 불일치; file={name}")

    encoder = manifest["encoder"]
    snapshot_download(
        encoder["repo_id"],
        revision=encoder["revision"],
        local_dir=_CONTENTVEC_DIR,
        allow_patterns=["config.json", encoder["filename"]],
    )
    if sha256(_CONTENTVEC_DIR / encoder["filename"]) != encoder["sha256"]:
        raise ValueError("ContentVec 가중치 해시 불일치")
