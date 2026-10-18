from pathlib import Path

MIMIC_REVISION = "b1ba78905267833282c3aceaeb9f0ec02f26f386"
MIMIC_VERSION = "parrot-mimicry-judgment@v1.0.0"
MIMIC_DIR = Path("/var/task/models/mimic")
CONTENTVEC_DIR = Path("/var/task/models/contentvec")


if __name__ == "__main__":
    import hashlib
    import json

    from huggingface_hub import snapshot_download

    snapshot_download(
        "buddybird-ai/parrot-mimicry-judgment",
        revision=MIMIC_REVISION,
        local_dir=MIMIC_DIR,
        allow_patterns=["judge/*", "manifest.json", "*.npz", "*.npy"],
    )

    manifest = json.loads((MIMIC_DIR / "manifest.json").read_text())

    for name, file in manifest["files"].items():
        with (MIMIC_DIR / name).open("rb") as data:
            digest = hashlib.file_digest(data, "sha256").hexdigest()

        if digest != file["sha256"].removeprefix("sha256:"):
            raise ValueError(f"모사 판정 번들 해시 불일치; file={name}")

    encoder = manifest["encoder"]

    snapshot_download(
        encoder["repo_id"],
        revision=encoder["revision"],
        local_dir=CONTENTVEC_DIR,
        allow_patterns=["config.json", encoder["filename"]],
    )

    with (CONTENTVEC_DIR / encoder["filename"]).open("rb") as data:
        digest = hashlib.file_digest(data, "sha256").hexdigest()

    if digest != encoder["sha256"]:
        raise ValueError("ContentVec 가중치 해시 불일치")
