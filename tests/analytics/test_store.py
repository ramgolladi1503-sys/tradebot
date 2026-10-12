from __future__ import annotations

import json
from pathlib import Path

from core.analytics.store import _trade_outcome_from_row, load_decision_telemetry_events


def test_load_decision_telemetry_skips_bad_jsonl_line(tmp_path: Path):
    path = tmp_path / "decision_events.jsonl"
    row = {
        "ts_epoch_ms": 1772164800000,
        "symbol": "NIFTY",
        "side": "BUY",
        "strike": 22500,
        "option_type": "CE",
        "execution_allowed": 0,
        "reject_reason": "spread_too_wide",
    }
    path.write_text("not-json\n" + json.dumps(row) + "\n", encoding="utf-8")

    events = load_decision_telemetry_events(paths=[path])

    assert len(events) == 1
    assert events[0].symbol == "NIFTY"
    assert events[0].intent == "rejected"


def test_store_preserves_unassessed_execution_status_and_explicit_false():
    outcome = _trade_outcome_from_row(
        {
            "event_id": "out_evt",
            "trade_key": "NIFTY|2026-10-29|25000|CE|BUY",
            "symbol": "NIFTY",
            "expiry": "2026-10-29",
            "strike": 25000,
            "option_type": "CE",
            "side": "BUY",
            "ts_epoch_ms": 1791776700000,
            "outcome": "hit_target",
            "outcome_reason": "TARGET_FIRST",
            "exec_feasible": True,
            "exec_feasible_flags": {"outcome_path_observed": True, "execution_feasibility_status": "UNASSESSED"},
        },
        source="test",
    )

    assert outcome is not None
    assert outcome.exec_feasible is False
    assert outcome.exec_feasible_flags["execution_feasibility_status"] == "UNASSESSED"
