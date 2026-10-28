import logging
import sys
import tempfile
from pathlib import Path
from typing import Any

import boto3

from app import config, display_score
from app.mimic_judgment.config import MODEL_VERSION

logger = logging.getLogger(__name__)

_MODEL_DIR = Path("/var/task/models/mimic")

_s3 = boto3.client("s3")


def load_model() -> Any:
    sys.path.insert(0, str(_MODEL_DIR))

    from judge import ContentVecEncoder, MimicryJudge, load_bundle

    bundle = load_bundle(_MODEL_DIR, verify=False)
    model = MimicryJudge(
        bundle,
        ContentVecEncoder(
            repo_id="/var/task/models/contentvec",
            layer=int(bundle.manifest["model"]["layer"]),
            weights_filename=None,
            weights_sha256=None,
        ),
    )

    model.encoder.load()

    logger.info(
        "모사 판정 모델 로드 완료; version=%s threshold=%.4f", MODEL_VERSION, display_score.mimic(bundle.threshold)
    )

    return model


def judge(model: Any, *, target_object_key: str, word_name: str, reference_object_keys: list[str]) -> Any:
    object_keys = [target_object_key, *reference_object_keys]

    with tempfile.TemporaryDirectory() as directory:
        paths = [Path(directory) / f"{index}{Path(object_key).suffix}" for index, object_key in enumerate(object_keys)]

        for object_key, path in zip(object_keys, paths, strict=True):
            _s3.download_file(config.S3_BUCKET, object_key, str(path))

        return model.judge_audio(paths[0], word_name, paths[1:])
