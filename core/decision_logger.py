from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict

from config import config as cfg


DECISION_JSONL = Path("logs/decision_events.jsonl")


def _conn():
    Path(cfg.TRADE_DB_PATH).parent.mkdir(exist_ok=True)
    return sqlite3.connect(cfg.TRADE_DB_PATH)


def _init_db():
    with _conn() as conn:
        conn.execute(
            """
        CREATE TABLE IF NOT EXISTS decision_events (
            trade_id TEXT PRIMARY KEY,
            ts TEXT,
            symbol TEXT,
            strategy_id TEXT,
            regime TEXT,
            regime_probs TEXT,
            shock_score REAL,
            side TEXT,
            instrument TEXT,
            dte REAL,
            expiry_bucket TEXT,
            score_0_100 REAL,
            xgb_proba REAL,
            deep_proba REAL,
            micro_proba REAL,
            ensemble_proba REAL,
            ensemble_uncertainty REAL,
            bid REAL,
            ask REAL,
            spread_pct REAL,
            bid_qty REAL,
            ask_qty REAL,
            depth_imbalance REAL,
            fill_prob_est REAL,
            portfolio_equity REAL,
            daily_pnl REAL,
            drawdown_pct REAL,
            loss_streak REAL,
            open_risk REAL,
            delta_exposure REAL,
            gamma_exposure REAL,
            vega_exposure REAL,
            gatekeeper_allowed INTEGER,
            veto_reasons TEXT,
            risk_allowed INTEGER,
            exec_guard_allowed INTEGER,
            action_size_multiplier REAL,
            filled_bool INTEGER,
            fill_price REAL,
            time_to_fill REAL,
            slippage_vs_mid REAL,
            pnl_horizon_5m REAL,
            pnl_horizon_15m REAL,
            mae_15m REAL,
            mfe_15m REAL
        )
        """
        )


def log_decision(event: Dict[str, Any]):
    _init_db()
    trade_id = event.get("trade_id") or event.get("decision_id")
    if not trade_id:
        return None

    # Normalize JSON fields
    if isinstance(event.get("regime_probs"), dict):
        event["regime_probs"] = json.dumps(event.get("regime_probs"))
    if isinstance(event.get("veto_reasons"), (list, dict)):
        event["veto_reasons"] = json.dumps(event.get("veto_reasons"))

    DECISION_JSONL.parent.mkdir(exist_ok=True)
    with DECISION_JSONL.open("a") as f:
        f.write(json.dumps(event, default=str) + "\n")

    cols = [
        "trade_id",
        "ts",
        "symbol",
        "strategy_id",
        "regime",
        "regime_probs",
        "shock_score",
        "side",
        "instrument",
        "dte",
        "expiry_bucket",
        "score_0_100",
        "xgb_proba",
        "deep_proba",
        "micro_proba",
        "ensemble_proba",
        "ensemble_uncertainty",
        "bid",
        "ask",
        "spread_pct",
        "bid_qty",
        "ask_qty",
        "depth_imbalance",
        "fill_prob_est",
        "portfolio_equity",
        "daily_pnl",
        "drawdown_pct",
        "loss_streak",
        "open_risk",
        "delta_exposure",
        "gamma_exposure",
        "vega_exposure",
        "gatekeeper_allowed",
        "veto_reasons",
        "risk_allowed",
        "exec_guard_allowed",
        "action_size_multiplier",
        "filled_bool",
        "fill_price",
        "time_to_fill",
        "slippage_vs_mid",
        "pnl_horizon_5m",
        "pnl_horizon_15m",
        "mae_15m",
        "mfe_15m",
    ]
    values = [event.get(c) for c in cols]
    with _conn() as conn:
        conn.execute(
            f"""
            INSERT OR REPLACE INTO decision_events
            ({",".join(cols)}) VALUES ({",".join(["?"] * len(cols))})
            """,
            values,
        )
    return trade_id


def update_execution(trade_id: str, exec_fields: Dict[str, Any]):
    if not trade_id:
        return
    _init_db()
    fields = exec_fields.copy()
    if isinstance(fields.get("veto_reasons"), (list, dict)):
        fields["veto_reasons"] = json.dumps(fields["veto_reasons"])
    sets = ", ".join([f"{k} = ?" for k in fields.keys()])
    vals = list(fields.values()) + [trade_id]
    with _conn() as conn:
        conn.execute(f"UPDATE decision_events SET {sets} WHERE trade_id = ?", vals)


def update_outcome(trade_id: str, outcome_fields: Dict[str, Any]):
    if not trade_id:
        return
    _init_db()
    sets = ", ".join([f"{k} = ?" for k in outcome_fields.keys()])
    vals = list(outcome_fields.values()) + [trade_id]
    with _conn() as conn:
        conn.execute(f"UPDATE decision_events SET {sets} WHERE trade_id = ?", vals)
