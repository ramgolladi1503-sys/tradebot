from __future__ import annotations

import json
from pathlib import Path

import pytest

import core.candidate_outcome_tracker as outcome_tracker
from core.candidate_outcome_truth import NOT_EXECUTABLE, STOP_HIT, TARGET_HIT, TIMEOUT


def _journal_row(**overrides: object) -> dict[str, object]:
    row = {
        "candidate_id": "cand-1",
        "trade_id": "trade-1",
        "strategy_family": "breakout",
        "symbol": "NIFTY",
        "index": "NIFTY",
        "regime": "LIVE",
        "expiry_type": "WEEKLY",
        "signal_epoch": 100.0,
        "entry_price": 100.0,
        "stop_loss_price": 95.0,
        "target_price": 110.0,
        "permission": "EXECUTE",
        "final_action": "EXECUTE",
        "execution_status": "executable",
        "readiness": "READY",
        "execution_entry_status": "executable",
        "candidate_status": "executable",
        "reportable_executable": True,
        "execution_allowed": True,
        "fallback_used": False,
        "row_kind": "candidate",
        "candidate_origin": "trade_builder",
        "candidate_class": "primary",
        "quote_source": "tick_store",
        "quantity": 2.0,
        "lot_size": 50.0,
        "risk_per_unit": 10.0,
        "brokerage": 1.0,
        "taxes": 0.5,
        "slippage_ticks": 1.0,
        "tick_size": 0.05,
    }
    row.update(overrides)
    return row


def test_tracker_target_hit_builds_default_windows() -> None:
    rows = outcome_tracker.build_candidate_outcome_records(
        [_journal_row()],
        observations={
            "cand-1": [
                {"observed_epoch": 101.0, "ltp": 104.0},
                {"observed_epoch": 102.0, "ltp": 110.0},
            ]
        },
    )

    assert [row["window_sec"] for row in rows] == [300, 600, 900, 1800]
    assert all(row["outcome_status"] == TARGET_HIT for row in rows)
    assert all(row["target_hit"] is True for row in rows)
    assert all(row["read_only"] is True for row in rows)
    assert all(row["append"] is False for row in rows)
    assert all(row["is_order_action"] is False for row in rows)
    assert all(row["broker_api_called"] is False for row in rows)
    assert all(row["setup_id"].startswith("breakout__LIVE__") for row in rows)


def test_tracker_stop_hit() -> None:
    rows = outcome_tracker.build_candidate_outcome_records(
        [_journal_row(trade_id="trade-stop")],
        observations={
            "cand-1": [
                {"observed_epoch": 101.0, "ltp": 98.0},
                {"observed_epoch": 102.0, "ltp": 94.0},
            ]
        },
        windows_sec=(300,),
    )

    assert rows
    assert rows[0]["window_sec"] == 300
    row = rows[0]
    assert row["outcome_status"] == STOP_HIT
    assert row["stop_hit"] is True
    assert row["target_hit"] is False


def test_tracker_timeout() -> None:
    rows = outcome_tracker.build_candidate_outcome_records(
        [_journal_row(trade_id="trade-timeout")],
        observations={
            "cand-1": [
                {"observed_epoch": 150.0, "ltp": 104.0},
                {"observed_epoch": 250.0, "ltp": 104.5},
            ]
        },
        windows_sec=(300,),
    )

    assert rows
    assert rows[0]["window_sec"] == 300
    row = rows[0]
    assert row["outcome_status"] == TIMEOUT
    assert row["timeout_hit"] is True
    assert row["first_hit_epoch"] is None
    assert row["observation_count"] == 2
    assert row["window_sec"] == 300


def test_tracker_non_executable_candidate_returns_not_executable() -> None:
    rows = outcome_tracker.build_candidate_outcome_records(
        [_journal_row(permission="QUEUE_ONLY", final_action="QUEUE_ONLY", execution_status="queue_only", readiness="QUEUE_ONLY", reportable_executable=False, execution_allowed=False, candidate_status="advisory_only")],
        observations={
            "cand-1": [
                {"observed_epoch": 101.0, "ltp": 120.0},
            ]
        },
        windows_sec=(300,),
    )

    assert rows
    assert rows[0]["window_sec"] == 300
    row = rows[0]
    assert row["outcome_status"] == NOT_EXECUTABLE
    assert row["outcome_reason"] == "candidate_not_reportable_or_execution_not_allowed"
    assert row["source_reportable_executable"] is False
    assert row["source_execution_allowed"] is False


def test_tracker_fallback_candidate_returns_not_executable() -> None:
    rows = outcome_tracker.build_candidate_outcome_records(
        [_journal_row(row_kind="recovered_fallback", quote_source="rest_fallback")],
        observations={
            "cand-1": [
                {"observed_epoch": 101.0, "ltp": 120.0},
            ]
        },
        windows_sec=(300,),
    )

    assert rows
    assert rows[0]["window_sec"] == 300
    row = rows[0]
    assert row["outcome_status"] == NOT_EXECUTABLE
    assert row["source_reportable_executable"] is True
    assert row["source_execution_allowed"] is True
    assert row["read_only"] is True
    assert row["append"] is False


def test_tracker_cost_adjusted_r_equals_gross_minus_cost() -> None:
    rows = outcome_tracker.build_candidate_outcome_records(
        [_journal_row()],
        observations={
            "cand-1": [
                {"observed_epoch": 101.0, "ltp": 104.0, "bid": 103.5, "ask": 104.5, "spread": 1.0},
                {"observed_epoch": 102.0, "ltp": 110.0, "bid": 109.5, "ask": 110.5, "spread": 1.0},
            ]
        },
        windows_sec=(300,),
    )

    row = rows[0]
    assert row["outcome_status"] == TARGET_HIT
    assert row["cost_adjusted_r"] == row["gross_r"] - row.get("estimated_cost_r", 0.0)
    assert row["cost_model_status"] == "READY"
    assert row["estimated_cost_abs"] > 0
    assert row["estimated_cost_r"] is not None
    assert row["spread_cost_abs"] > 0
    assert row["slippage_cost_abs"] > 0
    assert row["fee_cost_abs"] > 0
    assert row["effective_entry"] is not None
    assert row["effective_exit"] is not None
    assert row["setup_family"] == "breakout"
    assert row["setup_id"].startswith("breakout__LIVE__")


def test_tracker_write_failure_is_non_fatal(monkeypatch, tmp_path: Path) -> None:
    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(outcome_tracker, "_write_jsonl_rows", _boom)
    path, ok = outcome_tracker.write_candidate_outcome_records(
        [{"candidate_id": "cand-x", "trade_id": "trade-x"}],
        path=tmp_path / "candidate_outcomes.jsonl",
    )

    assert ok is False
    assert path == tmp_path / "candidate_outcomes.jsonl"


def test_tracker_can_write_jsonl(tmp_path: Path) -> None:
    rows = outcome_tracker.build_candidate_outcome_records(
        [_journal_row()],
        observations={
            "cand-1": [
                {"observed_epoch": 101.0, "ltp": 104.0},
                {"observed_epoch": 102.0, "ltp": 110.0},
            ]
        },
        windows_sec=(300,),
    )
    path, ok = outcome_tracker.write_candidate_outcome_records(rows, path=tmp_path / "candidate_outcomes.jsonl")

    assert ok is True
    assert path.exists()
    written = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    assert written[0]["window_sec"] == 300
    assert written[0]["outcome_status"] == TARGET_HIT


def test_tracker_module_avoids_broker_and_order_imports() -> None:
    source = Path(outcome_tracker.__file__).read_text(encoding="utf-8")
    forbidden = ("broker", "order_router", "live_trade", "kite", "upstox")
    assert not any(f"from core.{name}" in source or f"import {name}" in source for name in forbidden)
