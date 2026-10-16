import os
import tempfile
from pathlib import Path
from typing import Any

import boto3

from app.mimic.judgment import MimicJudgment, WordJudgment

_s3 = boto3.client("s3")


def _download(object_key: str, directory: Path) -> Path:
    path = directory / f"{len(list(directory.iterdir()))}{Path(object_key).suffix}"
    s3_object = _s3.get_object(Bucket=os.environ["AUDIO_S3_BUCKET"], Key=object_key)
    path.write_bytes(s3_object["Body"].read())
    return path


def analyze(
    model: MimicJudgment,
    *,
    account_id: str,
    species: str | None,
    object_key: str,
    words: list[dict[str, Any]],
) -> list[WordJudgment]:
    with tempfile.TemporaryDirectory() as directory:
        query_path = _download(object_key, Path(directory))
        word_paths = [
            (
                word["name"],
                [
                    _download(reference_key, Path(directory))
                    for reference_key in word["reference_object_keys"]
                ],
            )
            for word in words
        ]

        return model.judge(
            query_path, word_paths, account_id=account_id, species=species
        )
