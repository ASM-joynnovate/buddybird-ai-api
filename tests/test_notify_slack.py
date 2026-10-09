import json
import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO = "https://github.com/ASM-joynnovate/buddybird-ai-api"
SHA = "a" * 40
ROW_PREFIX = f"• <{REPO}/commit/{SHA}|{SHA[:7]}> fix ("
AUTHOR_AT_LIMIT = 3000 - len("*커밋*\n" + ROW_PREFIX + ")")


@pytest.mark.parametrize(
    ("count", "subject", "author", "truncated"),
    [
        (0, "fix", "dev", False),
        (1, "fix", "dev", False),
        (20, "fix", "dev", False),
        (21, "fix", "dev", True),
        (20, "배포 수정 & <검증> " * 6, "개발자 & 팀", True),
        (1, "fix", "a" * (AUTHOR_AT_LIMIT - 1), False),
        (1, "fix", "a" * AUTHOR_AT_LIMIT, False),
        (1, "fix", "a" * (AUTHOR_AT_LIMIT + 1), True),
    ],
    ids=[
        "empty",
        "short",
        "20-commits",
        "21-commits",
        "escaped",
        "2999",
        "3000",
        "3001",
    ],
)
def test_slack_commit_section_limit(
    count: int, subject: str, author: str, truncated: bool
) -> None:
    action = (
        Path(__file__).parents[1] / ".github/actions/notify-slack/action.yml"
    ).read_text()
    script = textwrap.dedent(action.split("      run: |\n", 1)[1])
    # Execute the real action while replacing git input and webhook delivery.
    script = 'git() { printf "%s" "$TEST_GIT_LOG"; }\ncurl() { cat; }\n' + script
    bash = shutil.which("bash")
    assert bash is not None
    result = subprocess.run(  # noqa: S603
        [bash, "-e", "-o", "pipefail", "-c", script],
        env={
            **os.environ,
            "WEBHOOK_URL": "https://example.invalid/webhook",
            "TITLE": "배포 결과",
            "FIELDS": "환경=prod",
            "BUTTONS": f"변경 내역={REPO}/compare/before...after",
            "COMMIT_RANGE": "before..after",
            "REPO_URL": REPO,
            "TEST_GIT_LOG": f"{SHA}\x1f{subject}\x1f{author}\n" * count,
        },
        capture_output=True,
        text=True,
        check=True,
    )
    blocks = json.loads(result.stdout)["blocks"]
    sections = [
        b["text"]["text"] for b in blocks if "text" in b and b["type"] == "section"
    ]
    if count == 0:
        assert sections == []
        return

    [commits] = sections
    assert len(commits) <= 3000
    assert ("이하 생략" in commits) == truncated
    if truncated:
        assert f"<{REPO}/compare/before...after|전체 변경 내역>" in commits
    else:
        assert commits.count("• ") == count

    def escape(value: str) -> str:
        return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    expected_row = (
        f"• <{REPO}/commit/{SHA}|{SHA[:7]}> {escape(subject[:80])} ({escape(author)})"
    )
    rows = [line for line in commits.splitlines() if line.startswith("• ")]
    assert all(row == expected_row for row in rows)
    if count > 1:
        assert rows
