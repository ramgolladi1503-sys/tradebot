from __future__ import annotations

import hashlib
import json
from pathlib import Path

from core.replay_harness import record_snapshot_decision, replay_from_file


def _hash_rows(rows: list[dict]) -> str:
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_session_replay_is_deterministic(tmp_path, monkeypatch):
    day = "20260304"
    monkeypatch.setattr("core.replay_harness.data_root", lambda: tmp_path / "data")

    snapshot = {
        "snapshot_id": "snap-1",
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
    )
    second = record_snapshot_decision(
        snapshot=dict(snapshot, snapshot_id="snap-2", timestamp_epoch=1772615460.0),
        meta=dict(meta, ts_epoch=1772615460.0),
        market=dict(market, spot=24805.0),
        signals=dict(signals),
        strategy=dict(strategy),
        risk=dict(risk),
        outcome={"status": "rejected", "reject_reasons": ["spread_too_wide"]},
        strategy_family="trend",
        day=day,
    )

    expected_session_path = tmp_path / "data" / "recordings" / day / "session.jsonl"
    assert Path(second["session_path"]) == expected_session_path
    assert Path(first["session_path"]).exists()

    replay_a = replay_from_file(expected_session_path, strict=True)
    replay_b = replay_from_file(expected_session_path, strict=True)
    assert replay_a == replay_b
    assert _hash_rows(replay_a) == _hash_rows(replay_b)
    assert len(replay_a) == 2
    assert replay_a[0]["match"] is True
    assert replay_a[1]["match"] is True
