import json
from pathlib import Path

import sqlite3
import pytest

from config import config as cfg
from core import decision_logger


def test_decision_logger_roundtrip(tmp_path, monkeypatch):
    db_path = tmp_path / "trades.db"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path))

    event = {
        "trade_id": "T1",
        "ts": "2026-02-05T10:00:00",
        "symbol": "NIFTY",
        "strategy_id": "TEST",
        "regime": "RANGE",
        "regime_probs": {"RANGE": 0.7},
        "shock_score": 0.1,
        "side": "BUY",
        "instrument": "OPT",
        "dte": 2,
        "expiry_bucket": "WEEKLY",
        "score_0_100": 80,
        "xgb_proba": 0.62,
        "deep_proba": None,
        "micro_proba": None,
        "ensemble_proba": 0.6,
        "ensemble_uncertainty": 0.2,
        "bid": 100,
        "ask": 102,
        "spread_pct": 0.02,
        "bid_qty": 100,
        "ask_qty": 120,
        "depth_imbalance": 0.1,
        "fill_prob_est": 0.7,
        "portfolio_equity": 100000,
        "equity": 100000,
        "equity_high": 100000,
        "daily_pnl": 0.0,
        "daily_pnl_pct": 0.0,
        "drawdown_pct": 0.0,
        "loss_streak": 0,
        "open_risk": 0.0,
        "open_risk_pct": 0.0,
        "delta_exposure": 0.0,
        "gamma_exposure": 0.0,
        "vega_exposure": 0.0,
        "gatekeeper_allowed": 1,
        "veto_reasons": [],
        "risk_allowed": None,
        "exec_guard_allowed": None,
        "action_size_multiplier": None,
        "filled_bool": None,
        "fill_price": None,
        "time_to_fill": None,
        "slippage_vs_mid": None,
        "pnl_horizon_5m": None,
        "pnl_horizon_15m": None,
        "mae_15m": None,
        "mfe_15m": None,
    }

    decision_logger.log_decision(event)
    decision_logger.update_execution("T1", {"risk_allowed": 1, "exec_guard_allowed": 1})
    decision_logger.update_outcome("T1", {"pnl_horizon_5m": 1.2})

    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT trade_id, risk_allowed, exec_guard_allowed, pnl_horizon_5m FROM decision_events WHERE trade_id='T1'").fetchone()
    conn.close()

    assert row == ("T1", 1, 1, 1.2)
