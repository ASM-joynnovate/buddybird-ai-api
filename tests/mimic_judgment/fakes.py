import math
from pathlib import Path
from types import SimpleNamespace
from typing import Any


class FakeMimicJudgmentModel:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def judge_audio(self, query: Path, word: str, own: list[Path]) -> SimpleNamespace:
        self.calls.append(
            {
                "target": query.read_bytes(),
                "word_name": word,
                "references": [(path.suffix, path.read_bytes()) for path in own],
            }
        )

        return SimpleNamespace(
            status="ok" if own else "no_reference",
            is_success=bool(own),
            percentile=0.995 if own else math.nan,
            n_own=len(own),
            n_fill=20 - len(own) if own else 0,
            set_size=20 if own else 0,
        )


class FakeMimicJudgmentR2:
    def download_file(self, _bucket: str, key: str, filename: str) -> None:
        if key.startswith("missing/"):
            raise KeyError(key)

        Path(filename).write_bytes(key.encode())
