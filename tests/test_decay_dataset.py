import json
from pathlib import Path

import pandas as pd

import pytest

from ml.decay_dataset import build_decay_dataset


def _write_jsonl(path: Path, rows):
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_decay_dataset_builds(tmp_path):
    pytest.importorskip("pyarrow")
    decision_path = tmp_path / "decision_events.jsonl"
    out_path = tmp_path / "decay.parquet"

    base_ts = pd.Timestamp("2026-02-01T09:15:00")
    rows = []
    for i in range(6):
        rows.append({
            "trade_id": f"T{i}",
            "ts": (base_ts + pd.Timedelta(minutes=i)).isoformat(),
            "strategy_id": "S1",
            "filled_bool": 1,
            "pnl_horizon_15m": 5 if i < 3 else -5,
            "ensemble_proba": 0.6,
            "regime": "TREND" if i < 3 else "RANGE",
            "gatekeeper_allowed": 1,
            "risk_allowed": 1,
            "exec_guard_allowed": 1,
            "bid": 100.0,
            "ask": 101.0,
            "spread_pct": 0.01,
            "shock_score": 0.2,
            "slippage_vs_mid": 0.1,
        })
    _write_jsonl(decision_path, rows)

    df = build_decay_dataset(
        decision_jsonl=decision_path,
        trade_log_path=tmp_path / "missing_trade_log.json",
        window=3,
        drawdown_threshold=-1.0,
        out_path=out_path,
    )

    assert not df.empty
    assert "expectancy" in df.columns
    assert "regime_js" in df.columns
    assert out_path.exists()


def test_regime_js_divergence(tmp_path):
    pytest.importorskip("pyarrow")
    decision_path = tmp_path / "decision_events.jsonl"
    out_path = tmp_path / "decay.parquet"

    base_ts = pd.Timestamp("2026-02-01T09:15:00")
    rows = []
    for i in range(6):
        rows.append({
            "trade_id": f"T{i}",
            "ts": (base_ts + pd.Timedelta(minutes=i)).isoformat(),
            "strategy_id": "S2",
            "filled_bool": 1,
            "pnl_horizon_15m": 1,
            "ensemble_proba": 0.55,
            "regime": "TREND" if i < 3 else "RANGE",
            "gatekeeper_allowed": 1,
            "risk_allowed": 1,
            "exec_guard_allowed": 1,
            "bid": 100.0,
            "ask": 101.0,
            "spread_pct": 0.01,
            "shock_score": 0.2,
            "slippage_vs_mid": 0.1,
        })
    _write_jsonl(decision_path, rows)

    df = build_decay_dataset(
        decision_jsonl=decision_path,
        trade_log_path=tmp_path / "missing_trade_log.json",
        window=3,
        out_path=out_path,
    )

    assert (df["regime_js"] > 0).any()
