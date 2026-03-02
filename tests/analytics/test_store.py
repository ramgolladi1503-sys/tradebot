from __future__ import annotations

import json
from pathlib import Path

from core.analytics.store import load_decision_telemetry_events


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
