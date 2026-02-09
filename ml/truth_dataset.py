import json
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple

import pandas as pd

from config import config as cfg


DECISION_JSONL = Path(getattr(cfg, "DECISION_LOG_PATH", "logs/decision_events.jsonl"))
DECISION_SQLITE = Path(cfg.TRADE_DB_PATH)


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def _read_sqlite(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM decision_events").fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _parse_ts(val) -> Optional[datetime]:
    if val is None:
        return None
    try:
        return datetime.fromisoformat(str(val))
    except Exception:
        return None


def _safe_json(val):
    if val is None:
        return None
    if isinstance(val, (dict, list)):
        return json.dumps(val)
    try:
        json.loads(val)
        return val
    except Exception:
        return json.dumps(val)


def _load_decay_state() -> tuple[dict, dict]:
    state_path = Path("logs/strategy_decay_state.json")
    prob_path = Path("logs/strategy_decay_probs.json")
    decay_state = {}
    decay_prob = {}
    if state_path.exists():
        try:
            obj = json.loads(state_path.read_text())
            decay_state = obj.get("decay_state", {}) or {}
        except Exception:
            decay_state = {}
    if prob_path.exists():
        try:
            decay_prob = json.loads(prob_path.read_text()) or {}
        except Exception:
            decay_prob = {}
    return decay_state, decay_prob


def build_truth_dataset(
    decision_jsonl: Path = DECISION_JSONL,
    decision_sqlite: Path = DECISION_SQLITE,
    out_parquet: Path = Path("data/truth_dataset.parquet"),
    out_csv: Optional[Path] = None,
) -> Tuple[pd.DataFrame, dict]:
    rows = _read_sqlite(decision_sqlite)
    if not rows:
        rows = _read_jsonl(decision_jsonl)
    if not rows:
        raise FileNotFoundError("No decision events found in JSONL or SQLite.")

    decay_state_map, decay_prob_map = _load_decay_state()
    out = []
    leakage_count = 0
    for r in rows:
        decision_id = r.get("decision_id") or r.get("trade_id")
        ts = r.get("ts") or r.get("timestamp")
        ts_dt = _parse_ts(ts)
        strategy_id = r.get("strategy_id")
        decay_state = decay_state_map.get(strategy_id)
        decay_prob = decay_prob_map.get(strategy_id)

        regime_probs = r.get("regime_probs")
        if isinstance(regime_probs, str):
            try:
                rp = json.loads(regime_probs)
                regime_probs = rp
            except Exception:
                regime_probs = None

        regime_entropy = r.get("regime_entropy")
        if regime_entropy is None and isinstance(regime_probs, dict) and regime_probs:
            try:
                import math
                probs = [float(v) for v in regime_probs.values() if v is not None]
                denom = sum(probs) or 1.0
                probs = [p / denom for p in probs]
                regime_entropy = -sum(p * math.log(p + 1e-9) for p in probs)
            except Exception:
                regime_entropy = None

        unstable_flag = r.get("unstable_regime_flag")
        if unstable_flag is None and regime_entropy is not None:
            try:
                unstable_flag = int(regime_entropy > float(getattr(cfg, "REGIME_ENTROPY_UNSTABLE", 1.5)))
            except Exception:
                unstable_flag = None

        outcome_ts = r.get("outcome_ts") or r.get("exit_ts") or r.get("exit_time") or r.get("filled_ts")
        outcome_dt = _parse_ts(outcome_ts)
        outcome_missing = False
        if outcome_dt and ts_dt and outcome_dt <= ts_dt:
            leakage_count += 1
            outcome_missing = True

        pnl_5m = r.get("pnl_horizon_5m")
        pnl_15m = r.get("pnl_horizon_15m")
        mae_15m = r.get("mae_15m")
        mfe_15m = r.get("mfe_15m")
        realized_pnl = r.get("realized_pnl") or r.get("pnl")
        realized_pnl_pct = r.get("realized_pnl_pct")
        if outcome_missing:
            pnl_5m = None
            pnl_15m = None
            mae_15m = None
            mfe_15m = None
            realized_pnl = None
            realized_pnl_pct = None

        if pnl_5m is None and pnl_15m is None and realized_pnl is None:
            outcome_missing = True

        quote_age = r.get("quote_age_sec")
        if quote_age is None and r.get("quote_ts_epoch") is not None:
            try:
                quote_age = max(0.0, datetime.utcnow().timestamp() - float(r.get("quote_ts_epoch")))
            except Exception:
                quote_age = None
        row = {
            "decision_id": decision_id,
            "ts": ts,
            "symbol": r.get("symbol"),
            "strategy_id": strategy_id,
            "instrument": r.get("instrument"),
            "side": r.get("side"),
            "qty_planned": r.get("qty_planned") or r.get("qty"),
            "qty_final": r.get("qty_final"),
            "size_multiplier": r.get("action_size_multiplier"),
            "score_0_100": r.get("score_0_100"),
            "bid": r.get("bid"),
            "ask": r.get("ask"),
            "spread_pct": r.get("spread_pct"),
            "bid_qty": r.get("bid_qty"),
            "ask_qty": r.get("ask_qty"),
            "depth_imbalance": r.get("depth_imbalance"),
            "quote_age_sec": quote_age,
            "quote_ts_epoch": r.get("quote_ts_epoch"),
            "depth_age_sec": r.get("depth_age_sec"),
            "primary_regime": r.get("primary_regime") or r.get("regime"),
            "regime_probs": _safe_json(regime_probs),
            "regime_entropy": regime_entropy,
            "unstable_regime_flag": unstable_flag,
            "shock_score": r.get("shock_score"),
            "uncertainty_index": r.get("uncertainty_index"),
            "fx_ret_5m": r.get("fx_ret_5m") or r.get("x_usdinr_ret5"),
            "vix_z": r.get("vix_z") or r.get("x_india_vix_z"),
            "crude_ret_15m": r.get("crude_ret_15m") or r.get("x_crude_ret15"),
            "corr_fx_nifty": r.get("corr_fx_nifty") or r.get("x_usdinr_corr_nifty"),
            "cross_asset_any_stale": r.get("cross_asset_any_stale"),
            "xgb_proba": r.get("xgb_proba"),
            "deep_proba": r.get("deep_proba"),
            "micro_proba": r.get("micro_proba"),
            "ensemble_proba": r.get("ensemble_proba"),
            "ensemble_uncertainty": r.get("ensemble_uncertainty"),
            "champion_proba": r.get("champion_proba"),
            "challenger_proba": r.get("challenger_proba"),
            "champion_model_id": r.get("champion_model_id"),
            "challenger_model_id": r.get("challenger_model_id"),
            "gatekeeper_allowed": r.get("gatekeeper_allowed"),
            "risk_allowed": r.get("risk_allowed"),
            "exec_guard_allowed": r.get("exec_guard_allowed"),
            "veto_reasons": _safe_json(r.get("veto_reasons")),
            "decay_state": decay_state,
            "decay_prob": decay_prob,
            "rl_shadow_only": r.get("rl_shadow_only"),
            "rl_suggested_multiplier": r.get("rl_suggested_multiplier"),
            "filled_bool": r.get("filled_bool"),
            "fill_price": r.get("fill_price"),
            "time_to_fill_sec": r.get("time_to_fill"),
            "slippage_vs_mid": r.get("slippage_vs_mid"),
            "exec_quality_score": r.get("exec_quality_score"),
            "missed_fill_reason": r.get("missed_fill_reason"),
            "pnl_5m": pnl_5m,
            "pnl_15m": pnl_15m,
            "mae_15m": mae_15m,
            "mfe_15m": mfe_15m,
            "realized_pnl": realized_pnl,
            "realized_pnl_pct": realized_pnl_pct,
            "drawdown_pct": r.get("drawdown_pct"),
            "daily_pnl_pct": r.get("daily_pnl_pct"),
            "outcome_missing": outcome_missing,
        }
        if row["filled_bool"] is None:
            if row.get("gatekeeper_allowed") == 0 or row.get("risk_allowed") == 0:
                row["filled_bool"] = False
                if not row.get("missed_fill_reason"):
                    row["missed_fill_reason"] = "rejected"
        out.append(row)

    df = pd.DataFrame(out)
    out_parquet.parent.mkdir(exist_ok=True)
    try:
        df.to_parquet(out_parquet, index=False)
    except Exception as e:
        raise RuntimeError(f"Failed to write parquet: {e}")
    if out_csv:
        df.to_csv(out_csv, index=False)

    report = {
        "total_decisions": int(len(df)),
        "leakage_count": int(leakage_count),
    }
    return df, report
