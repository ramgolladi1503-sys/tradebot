import json
from pathlib import Path

from scripts.run_rl_shadow_report import build_report, load_decision_events


def test_rl_shadow_report_builds(tmp_path: Path):
    data = [
        {
            "ts": "2026-02-05T10:00:00",
            "action_size_multiplier": 0.5,
            "pnl_horizon_15m": 100.0,
        },
        {
            "ts": "2026-02-05T11:00:00",
            "action_size_multiplier": 1.0,
            "pnl_horizon_15m": -50.0,
        },
        {
            "ts": "2026-02-06T10:00:00",
            "action_size_multiplier": 0.75,
            "pnl_horizon_15m": 40.0,
        },
    ]
    path = tmp_path / "decision_events.jsonl"
    with path.open("w") as f:
        for row in data:
            f.write(json.dumps(row) + "\n")

    events = load_decision_events(path)
    report = build_report(events)
    assert "days" in report
    day1 = [d for d in report["days"] if d["day"] == "2026-02-05"][0]
    assert day1["count"] == 2
    assert round(day1["baseline_pnl"], 2) == 50.0
    assert round(day1["rl_pnl"], 2) == 0.0
