from __future__ import annotations

import json
from pathlib import Path

import pytest

import dashboard.streamlit_app_runtime as runtime


pytestmark = [pytest.mark.ui_read_model, pytest.mark.safety, pytest.mark.regression]


def _write_snapshot(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"state": "ok", "payload": payload}),
        encoding="utf-8",
    )
    return path


def _install_reader(monkeypatch, ranked_path: Path, legacy_path: Path):
    calls: list[Path] = []

    def _read_snapshot(path):
        target = Path(path)
        calls.append(target)
        if not target.exists():
            return None
        return json.loads(target.read_text(encoding="utf-8"))

    monkeypatch.setattr(runtime, "RANKED_PIPELINE_LATEST_PATH", ranked_path)
    monkeypatch.setattr(runtime, "TOP_OPPORTUNITIES_LATEST_PATH", legacy_path)
    monkeypatch.setattr(runtime, "read_snapshot_payload", _read_snapshot)
    monkeypatch.setattr(runtime.cfg, "UI_LIVE_ROW_REQUIRE_TODAY", False, raising=False)
    return calls


def test_dashboard_preserves_canonical_rank_and_separates_fallback_advisory(tmp_path, monkeypatch):
    ranked_path = _write_snapshot(
        tmp_path / "runtime" / "ranked_pipeline_latest.json",
        {
            "top_executable_opportunities": [
                {
                    "trade_id": "EXEC-1",
                    "candidate_class": "EXECUTABLE",
                    "execution_allowed": True,
                    "selected_for_execution": True,
                    "rank_global": 1,
                    "rank_score": 0.84,
                    "execution_entry_status": "executable",
                    "execution_entry_source": "ask",
                    "source_flags": {"quote_source": "LIVE_WS"},
                },
                {
                    "trade_id": "EXEC-2",
                    "candidate_class": "EXECUTABLE",
                    "execution_allowed": True,
                    "selected_for_execution": False,
                    "rank_global": 2,
                    "rank_score": 0.71,
                    "execution_entry_status": "executable",
                    "execution_entry_source": "ask",
                    "source_flags": {"quote_source": "LIVE_WS"},
                },
            ],
            "top_advisory_opportunities": [
                {
                    "trade_id": "FALLBACK-1",
                    "candidate_class": "ADVISORY_ONLY",
                    "execution_allowed": False,
                    "selected_for_execution": False,
                    "rank_global": None,
                    "rank_score": 0.99,
                    "row_kind": "recovered_fallback",
                    "execution_entry_status": "advisory_only",
                    "source_flags": {
                        "quote_source": "REST_RECOVERY",
                        "recovered_fallback": True,
                    },
                }
            ],
        },
    )
    legacy_path = _write_snapshot(
        tmp_path / "runtime" / "top_opportunities_latest.json",
        {
            "top_executable_opportunities": [
                {
                    "trade_id": "LEGACY-EXEC",
                    "execution_allowed": True,
                    "rank_global": 0,
                }
            ],
            "top_advisory_opportunities": [],
        },
    )
    calls = _install_reader(monkeypatch, ranked_path, legacy_path)

    frames = runtime._load_top_opportunities_frames(limit=10)

    executable = frames["top_executable"]
    advisory = frames["top_advisory"]
    assert calls == [ranked_path]
    assert list(executable["trade_id"]) == ["EXEC-1", "EXEC-2"]
    assert list(executable["rank_global"]) == [1, 2]
    assert list(advisory["trade_id"]) == ["FALLBACK-1"]
    assert bool(advisory.iloc[0]["execution_allowed"]) is False
    assert advisory.iloc[0]["candidate_class"] == "ADVISORY_ONLY"
    assert set(executable["trade_id"]).isdisjoint(set(advisory["trade_id"]))
    assert "LEGACY-EXEC" not in set(executable["trade_id"])


def test_missing_canonical_snapshot_does_not_promote_legacy_rows(tmp_path, monkeypatch):
    ranked_path = tmp_path / "runtime" / "ranked_pipeline_latest.json"
    legacy_path = _write_snapshot(
        tmp_path / "runtime" / "top_opportunities_latest.json",
        {
            "top_executable_opportunities": [
                {"trade_id": "LEGACY-EXEC", "execution_allowed": True}
            ],
            "top_advisory_opportunities": [],
        },
    )
    calls = _install_reader(monkeypatch, ranked_path, legacy_path)

    frames = runtime._load_top_opportunities_frames(limit=10)

    assert calls == [ranked_path]
    assert frames["top_executable"].empty
    assert frames["top_advisory"].empty
