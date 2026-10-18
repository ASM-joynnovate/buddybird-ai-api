import os
import tempfile
from pathlib import Path

import boto3

from app.mimic.judgment import MimicJudgment, MimicResult

_s3 = boto3.client("s3")


def _download(object_key: str, directory: Path) -> Path:
    path = directory / f"{len(list(directory.iterdir()))}{Path(object_key).suffix}"
    s3_object = _s3.get_object(Bucket=os.environ["AUDIO_S3_BUCKET"], Key=object_key)
    path.write_bytes(s3_object["Body"].read())
    return path


def analyze(
    model: MimicJudgment,
    *,
    target_object_key: str,
    word_name: str,
    reference_object_keys: list[str],
) -> MimicResult:
    with tempfile.TemporaryDirectory() as directory:
        target_path = _download(target_object_key, Path(directory))
        reference_paths = [
            _download(object_key, Path(directory))
            for object_key in reference_object_keys
        ]

        return model.judge(target_path, word_name, reference_paths)
