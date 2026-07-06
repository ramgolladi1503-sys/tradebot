from __future__ import annotations

import json
from pathlib import Path

import dashboard.streamlit_app_runtime as runtime


def _write_snapshot(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"state": "ok", "payload": payload}), encoding="utf-8")
    return path


def test_dashboard_top_opportunities_reads_canonical_ranked_path_only(tmp_path, monkeypatch):
    ranked_path = _write_snapshot(
        tmp_path / "runtime" / "ranked_pipeline_latest.json",
        {
            "top_executable_opportunities": [],
            "top_advisory_opportunities": [
                {"trade_id": "DIRTY-1", "candidate_origin": "dirty_option_bridge", "execution_allowed": False}
            ],
        },
    )
    legacy_path = _write_snapshot(
        tmp_path / "runtime" / "top_opportunities_latest.json",
        {
            "top_executable_opportunities": [
                {"trade_id": "LEGACY-EXEC", "candidate_origin": "legacy_trade_builder", "execution_allowed": True}
            ],
            "top_advisory_opportunities": [],
        },
    )

    calls: list[Path] = []

    def _read_snapshot(path):
        calls.append(Path(path))
        return json.loads(Path(path).read_text(encoding="utf-8"))

    monkeypatch.setattr(runtime, "RANKED_PIPELINE_LATEST_PATH", ranked_path)
    monkeypatch.setattr(runtime, "TOP_OPPORTUNITIES_LATEST_PATH", legacy_path)
    monkeypatch.setattr(runtime, "read_snapshot_payload", _read_snapshot)

    frames = runtime._load_top_opportunities_frames(limit=10)

    assert calls == [ranked_path]
    assert "top_executable" in frames
    assert "top_advisory" in frames
    assert calls[0] == ranked_path
    assert frames["top_executable"].empty or "trade_id" in frames["top_executable"].columns
    assert frames["top_advisory"].empty or "trade_id" in frames["top_advisory"].columns
