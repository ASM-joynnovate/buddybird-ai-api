import logging
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.mimic.download import CONTENTVEC_DIR, MIMIC_DIR, MIMIC_REVISION

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True, kw_only=True)
class MimicResult:
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

        logger.info(
            "모사 판정 모델 로드 완료; revision=%s threshold=%.4f",
            MIMIC_REVISION,
            self._bundle.threshold,
        )

    def judge(
        self, target_path: Path, word_name: str, reference_paths: list[Path]
    ) -> MimicResult:
        target_features = self._encoder.extract_file(target_path)
        reference_waves = [self._judge.load_audio(path) for path in reference_paths]

        result = self._judge.judge(
            self._bundle,
            target_features,
            word_name,
            [
                self._encoder.extract(self._judge.preprocess(wave))
                for wave in reference_waves
            ],
            own_content_hashes=[
                self._judge.content_hash(wave) for wave in reference_waves
            ],
        )

        percentile = float(result.percentile)

        return MimicResult(
            status=result.status,
            is_success=result.is_success,
            score=None if math.isnan(percentile) else percentile,
            n_own=result.n_own,
            n_fill=result.n_fill,
            set_size=result.set_size,
        )
