from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RAW_PARQUET_PATH = "runtime/strategy_validation/resolved_option_ticks_20260702.parquet"


def _git(cwd: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=cwd, text=True, stderr=subprocess.PIPE
    ).strip()


def test_raw_tracked_parquet_is_excluded_from_lfs_filters():
    attributes = _git(ROOT, "check-attr", "filter", "diff", "merge", "text", "--", RAW_PARQUET_PATH)

    assert f"{RAW_PARQUET_PATH}: filter: unset" in attributes
    assert f"{RAW_PARQUET_PATH}: diff: unset" in attributes
    assert f"{RAW_PARQUET_PATH}: merge: unset" in attributes
    assert f"{RAW_PARQUET_PATH}: text: unset" in attributes


def test_raw_tracked_parquet_content_changes_remain_visible_to_git_status(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(tmp_path, "init", "--quiet", str(repo))
    _git(repo, "config", "user.name", "Attribute Regression Test")
    _git(repo, "config", "user.email", "attribute-test@example.invalid")

    attributes = (ROOT / ".gitattributes").read_text()
    (repo / ".gitattributes").write_text(attributes)
    parquet = repo / RAW_PARQUET_PATH
    parquet.parent.mkdir(parents=True)
    original = b"PAR1raw parquet fixture\x00"
    parquet.write_bytes(original)

    _git(repo, "add", ".gitattributes", RAW_PARQUET_PATH)
    _git(repo, "commit", "--quiet", "-m", "fixture")
    assert _git(repo, "status", "--porcelain") == ""

    parquet.write_bytes(original + b"changed")
    status = _git(repo, "status", "--porcelain")
    assert status.split(maxsplit=1) == ["M", RAW_PARQUET_PATH]
