from __future__ import annotations

import json
from pathlib import Path

from core.replay_harness import record_snapshot_decision, replay_from_file


def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = str(line).strip()
            if not text:
                continue
            rows.append(json.loads(text))
    return rows


def test_record_and_replay_is_deterministic(tmp_path):
    base_dir = tmp_path / "data" / "replay"
    day = "20260304"

    snapshot = {
        "snapshot_id": "snap-a",
        "timestamp_epoch": 1772615400.0,
        "index_price": 24800.0,
        "source": "sqlite",
    }
    meta = {
        "ts_epoch": 1772615400.0,
        "run_id": "RUN-1",
        "symbol": "NIFTY",
        "timeframe": "1m",
    }
    market = {
        "spot": 24800.0,
        "trend_state": "UP",
        "regime": "TREND",
        "vol_state": "LOW",
    }
    signals = {"pattern_flags": ["breakout"], "rank_score": 0.73, "confidence": 0.72}
    strategy = {
        "name": "trend_breakout",
        "direction": "BUY",
        "entry_reason": "breakout",
        "stop": 24750.0,
        "target": 24950.0,
        "rr": 3.0,
        "max_loss": 5000.0,
        "size": 1,
    }
    risk = {"daily_loss_limit": 0.02, "position_limit": 3, "slippage_bps_assumed": 8}

    first = record_snapshot_decision(
        snapshot=dict(snapshot),
        meta=dict(meta),
        market=dict(market),
        signals=dict(signals),
        strategy=dict(strategy),
        risk=dict(risk),
        outcome={"status": "planned", "reject_reasons": []},
        strategy_family="trend",
        day=day,
        base_dir=base_dir,
    )
    second = record_snapshot_decision(
        snapshot=dict(snapshot, snapshot_id="snap-b", timestamp_epoch=1772615460.0),
        meta=dict(meta, ts_epoch=1772615460.0),
        market=dict(market, spot=24805.0),
        signals=dict(signals),
        strategy=dict(strategy),
        risk=dict(risk),
        outcome={"status": "rejected", "reject_reasons": ["spread_too_wide"]},
        strategy_family="trend",
        day=day,
        base_dir=base_dir,
    )

    decision_path = Path(second["decision_path"])
    snapshot_path = Path(first["snapshot_path"])
    assert decision_path.exists()
    assert snapshot_path.exists()
    assert decision_path.parent.name == day

    replay_a = replay_from_file(decision_path, strict=True)
    replay_b = replay_from_file(decision_path, strict=True)
    assert replay_a == replay_b
    assert len(replay_a) == 2
    assert replay_a[0]["match"] is True
    assert replay_a[1]["match"] is True
    assert replay_a[1]["reject_reasons"] == ["spread_too_wide"]

    recorded_rows = _read_jsonl(decision_path)
    assert replay_a[0]["decision_id"] == recorded_rows[0]["recorded"]["decision_id"]
    assert replay_a[1]["decision_id"] == recorded_rows[1]["recorded"]["decision_id"]

