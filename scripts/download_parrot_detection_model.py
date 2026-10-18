import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

import onnx.utils
from huggingface_hub import hf_hub_download

revision = os.environ["PARROT_DETECTION_MODEL_REVISION"]
models = Path("/var/task/models")

models.mkdir(parents=True)

with tempfile.TemporaryDirectory() as cache_dir:
    manifest_path = hf_hub_download(
        "buddybird-ai/parrot-sound-gate",
        "model_manifest.json",
        revision=revision,
        cache_dir=cache_dir,
    )
    manifest = json.loads(Path(manifest_path).read_text())
    perch = manifest["perch"]

    shutil.copyfile(
        hf_hub_download(
            "buddybird-ai/parrot-sound-gate",
            manifest["model"]["filename"],
            revision=revision,
            cache_dir=cache_dir,
        ),
        models / "gate.joblib",
    )

    perch_path = hf_hub_download(perch["repo_id"], perch["filename"], revision=perch["revision"], cache_dir=cache_dir)

    # manifest 해시는 추출 전 원본 파일 기준
    with Path(perch_path).open("rb") as data:
        digest = hashlib.file_digest(data, "sha256").hexdigest()

    if digest != perch["sha256"]:
        raise ValueError("Perch 가중치 해시 불일치")

    onnx.utils.extract_model(
        perch_path,
        models / "perch_embedding.onnx",
        ["inputs"],
        ["embedding"],
        infer_shapes=False,
    )

with (models / "gate.joblib").open("rb") as data:
    digest = hashlib.file_digest(data, "sha256").hexdigest()

if digest != manifest["model"]["sha256"]:
    raise ValueError("앵무새 소리 판별 모델 해시 불일치")
