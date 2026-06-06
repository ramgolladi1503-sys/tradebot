from __future__ import annotations

import json
from pathlib import Path

from core.agents.readers import discover_latest_existing_path, discover_runtime_artifacts, read_json_file, read_jsonl_file


def test_read_jsonl_file_skips_malformed_lines_and_supports_tail(tmp_path: Path):
    path = tmp_path / "events.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps({"event": "KEEP_1", "ts_epoch": 1}),
                "{not-json}",
                json.dumps({"event": "KEEP_2", "ts_epoch": 2}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert [row["event"] for row in read_jsonl_file(path)] == ["KEEP_1", "KEEP_2"]
    assert [row["event"] for row in read_jsonl_file(path, tail_lines=1)] == ["KEEP_2"]


def test_read_json_file_missing_returns_empty_dict(tmp_path: Path):
    assert read_json_file(tmp_path / "missing.json") == {}


def test_discover_latest_existing_path_prefers_newest(tmp_path: Path):
    older = tmp_path / "older.json"
    newer = tmp_path / "newer.json"
    older.write_text("{}", encoding="utf-8")
    newer.write_text("{}", encoding="utf-8")
    older.touch()
    newer.touch()

    assert discover_latest_existing_path([older, newer]) == newer


def test_discover_runtime_artifacts_handles_missing_directories(tmp_path: Path):
    artifacts = discover_runtime_artifacts(runtime_root=tmp_path / "runtime", logs_root=tmp_path / "logs", session_root=tmp_path / "runtime" / "live_sessions")
    assert artifacts["feed_runtime_logs"] is None
    assert artifacts["depth_ws_watchdog"] is None
