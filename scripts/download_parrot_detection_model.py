import json
import os
import shutil
import tempfile
from pathlib import Path

import onnx.utils
from huggingface_hub import hf_hub_download

tag = os.environ["PARROT_DETECTION_MODEL_TAG"]
models = Path("/var/task/models")

models.mkdir(parents=True)

with tempfile.TemporaryDirectory() as cache_dir:
    manifest_path = hf_hub_download(
        "buddybird-ai/parrot-sound-gate",
        "model_manifest.json",
        revision=tag,
        cache_dir=cache_dir,
    )
    manifest = json.loads(Path(manifest_path).read_text())
    perch = manifest["perch"]

    shutil.copyfile(
        hf_hub_download(
            "buddybird-ai/parrot-sound-gate",
            manifest["model"]["filename"],
            revision=tag,
            cache_dir=cache_dir,
        ),
        models / "gate.joblib",
    )

    onnx.utils.extract_model(
        hf_hub_download(perch["repo_id"], perch["filename"], revision=perch["revision"], cache_dir=cache_dir),
        models / "perch_embedding.onnx",
        ["inputs"],
        ["embedding"],
        infer_shapes=False,
    )
