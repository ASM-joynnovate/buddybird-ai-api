import io
from pathlib import Path
from typing import Any

from app.mimic.judgment import MimicJudgment, WordJudgment


class FakeMimic(MimicJudgment):
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def judge(
        self,
        query_path: Path,
        words: list[tuple[str, list[Path]]],
        *,
        account_id: str,
        species: str | None,
    ) -> list[WordJudgment]:
        self.calls.append(
            {
                "query": query_path.read_bytes(),
                "words": [
                    (word, [(path.suffix, path.read_bytes()) for path in paths])
                    for word, paths in words
                ],
                "account_id": account_id,
                "species": species,
            }
        )
        return [
            WordJudgment(
                status="ok" if paths else "no_reference",
                is_success=bool(paths),
                score=99.5 if paths else None,
                n_own=len(paths),
                n_fill=20 - len(paths) if paths else 0,
                set_size=20 if paths else 0,
            )
            for _, paths in words
        ]


class FakeMimicS3:
    def get_object(self, **params: str) -> dict[str, io.BytesIO]:
        if params["Key"].startswith("missing/"):
            raise KeyError(params["Key"])
        return {"Body": io.BytesIO(params["Key"].encode())}
