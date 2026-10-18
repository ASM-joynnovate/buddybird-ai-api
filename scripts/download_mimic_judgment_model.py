import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

from huggingface_hub import snapshot_download

model_dir = Path("/var/task/models/mimic")
encoder_dir = Path("/var/task/models/contentvec")

with tempfile.TemporaryDirectory() as cache_dir:
    # cache의 LFS 파일 권한 0400을 복사하지 않음
    shutil.copytree(
        snapshot_download(
            "buddybird-ai/parrot-mimicry-judgment",
            revision=os.environ["MIMIC_JUDGMENT_MODEL_REVISION"],
            cache_dir=cache_dir,
            allow_patterns=["judge/*", "manifest.json", "*.npz", "*.npy"],
        ),
        model_dir,
        copy_function=shutil.copyfile,
    )

    manifest = json.loads((model_dir / "manifest.json").read_text())
    encoder = manifest["encoder"]

    shutil.copytree(
        snapshot_download(
            encoder["repo_id"],
            revision=encoder["revision"],
            cache_dir=cache_dir,
            allow_patterns=["config.json", encoder["filename"]],
        ),
        encoder_dir,
        copy_function=shutil.copyfile,
    )

for name, file in manifest["files"].items():
    with (model_dir / name).open("rb") as data:
        digest = hashlib.file_digest(data, "sha256").hexdigest()

    if digest != file["sha256"].removeprefix("sha256:"):
        raise ValueError(f"모사 판정 번들 해시 불일치; file={name}")

with (encoder_dir / encoder["filename"]).open("rb") as data:
    digest = hashlib.file_digest(data, "sha256").hexdigest()

if digest != encoder["sha256"]:
    raise ValueError("ContentVec 가중치 해시 불일치")
