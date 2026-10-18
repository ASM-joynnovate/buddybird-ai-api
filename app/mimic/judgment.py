import logging
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.mimic.download import CONTENTVEC_DIR, MIMIC_DIR, MIMIC_REVISION

logger = logging.getLogger(__name__)


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
        sys.path.insert(0, str(MIMIC_DIR))
        import judge

        self._judge: Any = judge
        self._bundle = judge.load_bundle(MIMIC_DIR, verify=False)
        self._encoder = judge.ContentVecEncoder(
            repo_id=str(CONTENTVEC_DIR),
            layer=int(self._bundle.manifest["model"]["layer"]),
            weights_filename=None,
            weights_sha256=None,
        )
        self._encoder.load()
        self._lock = threading.Lock()

        logger.info(
            "모사 판정 모델 로드 완료; revision=%s threshold=%.4f",
            MIMIC_REVISION,
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
