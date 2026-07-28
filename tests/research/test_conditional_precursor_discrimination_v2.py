from pathlib import Path

import pandas as pd

from scripts.run_conditional_precursor_discrimination_v2 import (
    clustered_event_scope,
    is_lfs_pointer,
    stable_json,
)


def test_lfs_pointer_detection(tmp_path: Path) -> None:
    pointer = tmp_path / "sample.parquet"
    pointer.write_text(
        "version https://git-lfs.github.com/spec/v1\n"
        "oid sha256:0123456789abcdef\n"
        "size 123\n",
        encoding="utf-8",
    )
    assert is_lfs_pointer(pointer) is True


def test_regular_file_not_lfs_pointer(tmp_path: Path) -> None:
    regular = tmp_path / "sample.txt"
    regular.write_text("ordinary evidence", encoding="utf-8")
    assert is_lfs_pointer(regular) is False


def test_stable_json_is_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    payload = {"z": 1, "a": {"y": 2, "b": 3}}
    stable_json(first, payload)
    stable_json(second, payload)
    assert first.read_bytes() == second.read_bytes()


def test_clustered_event_scope_excludes_source_only_sessions() -> None:
    frame = pd.DataFrame(
        {
            "session": ["2026-01-01", "2026-01-01", "2026-01-02", "2026-01-03"],
            "move_cluster_id": ["a", None, "b", None],
            "is_expansion_event": [True, False, True, False],
        }
    )
    clustered = clustered_event_scope(frame, "move_cluster_id")
    assert clustered["move_cluster_id"].tolist() == ["a", "b"]
    assert clustered["session"].nunique() == 2
