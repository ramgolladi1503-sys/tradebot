from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.market_event_graph_contract import (
    DATASET_SHA256,
    FROZEN_DISCOVERY_SPEC_SHA256,
    FROZEN_THRESHOLDS,
    STRATEGY_ID,
)
from scripts.extract_market_event_graph_governed_session_v1 import extract_governed_session


def _row(*, minute: int, session_date: str = "2026-08-07", run_id: str = "run-1") -> dict:
    end = 1_786_090_000.0 + minute * 60.0
    returns = [0.0001 + index * 0.000001 for index in range(40)]
    return {
        "schema_version": 1,
        "source_kind": "LIVE_CAPTURED_METADATA",
        "run_id": run_id,
        "session_date": session_date,
        "universe_hash": "universe-a",
        "expected_constituents": 40,
        "market_event_graph_strategy_id": STRATEGY_ID,
        "market_event_graph_dataset_sha256": DATASET_SHA256,
        "market_event_graph_frozen_spec_sha256": FROZEN_DISCOVERY_SPEC_SHA256,
        "market_event_graph_thresholds": dict(FROZEN_THRESHOLDS),
        "completed_constituent_bars": [
            {
                "session_date": session_date,
                "ts_epoch": end,
                "source_bar_end_epoch": end,
                "completed": True,
                "index_ret1": 0.0002,
                "constituent_ret1": returns,
            }
        ],
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }


def _write(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def test_extracts_one_post_cas_session_without_outcome_fields(tmp_path: Path) -> None:
    source = tmp_path / "captured_metadata.jsonl"
    first = _row(minute=1)
    second = _row(minute=2)
    first["future_return_15"] = 999.0
    second["pnl"] = 999.0
    _write(source, [first, second])

    result = extract_governed_session(source, session_date="2026-08-07")

    assert result["market_event_graph_thresholds"] == FROZEN_THRESHOLDS
    assert [bar["source_bar_end_epoch"] for bar in result["completed_constituent_bars"]] == [
        1_786_090_120.0,
        1_786_090_180.0,
    ]
    bridge = result["governed_source_bridge"]
    assert bridge["source_regime"] == "POST_CAS"
    assert bridge["source_interval_count"] == 2
    assert bridge["source_run_id"] == "run-1"
    assert bridge["outcomes_opened"] is False
    serialized = json.dumps(result, sort_keys=True)
    assert "future_return_15" not in serialized
    assert '"pnl"' not in serialized


def test_classifies_fresh_pre_cas_lane(tmp_path: Path) -> None:
    source = tmp_path / "captured_metadata.jsonl"
    _write(source, [_row(minute=1, session_date="2026-07-30")])

    result = extract_governed_session(source, session_date="2026-07-30")

    assert result["governed_source_bridge"]["source_regime"] == "PRE_CAS_FRESH"


def test_rejects_consumed_session(tmp_path: Path) -> None:
    source = tmp_path / "captured_metadata.jsonl"
    _write(source, [_row(minute=1, session_date="2026-07-22")])

    with pytest.raises(ValueError, match="session_not_fresh"):
        extract_governed_session(source, session_date="2026-07-22")


def test_rejects_mixed_run_ids(tmp_path: Path) -> None:
    source = tmp_path / "captured_metadata.jsonl"
    _write(source, [_row(minute=1, run_id="run-a"), _row(minute=2, run_id="run-b")])

    with pytest.raises(ValueError, match="mixed_or_missing_run_ids"):
        extract_governed_session(source, session_date="2026-08-07")


def test_rejects_duplicate_or_nonincreasing_intervals(tmp_path: Path) -> None:
    source = tmp_path / "captured_metadata.jsonl"
    _write(source, [_row(minute=1), _row(minute=1)])

    with pytest.raises(ValueError, match="duplicate_or_nonincreasing_source_interval"):
        extract_governed_session(source, session_date="2026-08-07")


def test_rejects_frozen_contract_drift(tmp_path: Path) -> None:
    source = tmp_path / "captured_metadata.jsonl"
    row = _row(minute=1)
    row["market_event_graph_thresholds"]["breadth_high"] += 0.01
    _write(source, [row])

    with pytest.raises(ValueError, match="source_frozen_contract_mismatch"):
        extract_governed_session(source, session_date="2026-08-07")


def test_rejects_non_live_or_unsafe_source(tmp_path: Path) -> None:
    source = tmp_path / "captured_metadata.jsonl"
    replay = _row(minute=1)
    replay["source_kind"] = "REPLAY_FIXTURE"
    _write(source, [replay])
    with pytest.raises(ValueError, match="source_kind_not_live_captured_metadata"):
        extract_governed_session(source, session_date="2026-08-07")

    unsafe = _row(minute=1)
    unsafe["allowed_for_live_execution"] = True
    _write(source, [unsafe])
    with pytest.raises(ValueError, match="source_live_authority_violated"):
        extract_governed_session(source, session_date="2026-08-07")
