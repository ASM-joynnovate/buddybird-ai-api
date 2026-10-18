from pathlib import Path

GATE_REVISION = "v2.0.0"
GATE_PATH = Path("/var/task/models/gate.joblib")
PERCH_PATH = Path("/var/task/models/perch_embedding.onnx")


# Docker 빌드 단계에서 모델 파일 생성
if __name__ == "__main__":
    import shutil

    import onnx.utils
    from huggingface_hub import hf_hub_download

    GATE_PATH.parent.mkdir(parents=True, exist_ok=True)

    shutil.copyfile(
        hf_hub_download(
            "buddybird-ai/parrot-sound-gate",
            "gate-2.0.0.joblib",
            revision=GATE_REVISION,
        ),
        GATE_PATH,
    )

    onnx.utils.extract_model(
        hf_hub_download(
            "justinchuby/Perch-onnx",
            "perch_v2.onnx",
            revision="da88bf8c37c0b3068fc706fe509f633b9fbd28c1",
        ),
        PERCH_PATH,
        ["inputs"],
        ["embedding"],
        infer_shapes=False,
    )
