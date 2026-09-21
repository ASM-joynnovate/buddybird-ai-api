"""S3에서 오디오 클립을 다운로드해 numpy 배열로 반환한다."""

from __future__ import annotations

import asyncio
import io
import os

import numpy as np

_BUCKET = os.environ.get("AUDIO_S3_BUCKET", "")


def download_audio(s3_key: str, bucket: str = _BUCKET) -> tuple[np.ndarray, int]:
    import boto3
    import librosa

    client = boto3.client("s3")
    body = client.get_object(Bucket=bucket, Key=s3_key)["Body"].read()
    audio, sr = librosa.load(io.BytesIO(body), sr=None, mono=True)
    return audio.astype(np.float32), int(sr)


async def download_audio_async(
    s3_key: str, bucket: str = _BUCKET
) -> tuple[np.ndarray, int]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, download_audio, s3_key, bucket)
