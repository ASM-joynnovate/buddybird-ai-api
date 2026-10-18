import io
from pathlib import Path
from typing import Any

from app.mimic.judgment import MimicJudgment, MimicResult


class FakeMimic(MimicJudgment):
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def judge(
        self, target_path: Path, word_name: str, reference_paths: list[Path]
    ) -> MimicResult:
        self.calls.append(
            {
                "target": target_path.read_bytes(),
                "word_name": word_name,
                "references": [
                    (path.suffix, path.read_bytes()) for path in reference_paths
                ],
            }
        )
        return MimicResult(
            status="ok" if reference_paths else "no_reference",
            is_success=bool(reference_paths),
            score=0.995 if reference_paths else None,
            n_own=len(reference_paths),
            n_fill=20 - len(reference_paths) if reference_paths else 0,
            set_size=20 if reference_paths else 0,
        )


class FakeMimicS3:
    def get_object(self, **params: str) -> dict[str, io.BytesIO]:
        if params["Key"].startswith("missing/"):
            raise KeyError(params["Key"])
        return {"Body": io.BytesIO(params["Key"].encode())}
