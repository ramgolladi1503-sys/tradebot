import json
from pathlib import Path
from datetime import datetime

import pandas as pd

from config import config as cfg


def _time_bucket(ts: pd.Timestamp) -> str:
    if pd.isna(ts):
        return "UNKNOWN"
    h = ts.hour
    if h < 11:
        return "OPEN"
    if h < 14:
        return "MID"
    return "CLOSE"


def build_daily_audit(df: pd.DataFrame, day: str, out_path: Path) -> Path:
    if df is None or df.empty:
        raise ValueError("Truth dataset is empty.")

    df = df.copy()
    df["ts_dt"] = pd.to_datetime(df["ts"], errors="coerce")
    df = df[df["ts_dt"].dt.date.astype(str) == day]
    if df.empty:
        raise ValueError(f"No decisions found for date {day}.")

    executed = int(((df["gatekeeper_allowed"] == 1) & (df["risk_allowed"] == 1)).sum()) if "gatekeeper_allowed" in df.columns else 0
    rejected = int(len(df) - executed)
    filled = int((df["filled_bool"] == 1).sum()) if "filled_bool" in df.columns else 0
    missed = int(executed - filled)

    veto_counts = {}
    if "veto_reasons" in df.columns:
        for v in df["veto_reasons"].dropna().values:
            try:
                reasons = json.loads(v) if isinstance(v, str) else v
            except Exception:
                reasons = []
            if isinstance(reasons, str):
                reasons = [reasons]
            for r in reasons or []:
                veto_counts[r] = veto_counts.get(r, 0) + 1

    pnl_col = "realized_pnl" if "realized_pnl" in df.columns else "pnl_15m"
    pnl_series = df[pnl_col] if pnl_col in df.columns else pd.Series(dtype=float)

    df["time_bucket"] = df["ts_dt"].apply(_time_bucket)
    pnl_by_strategy = df.groupby("strategy_id")[pnl_col].sum().dropna().to_dict() if pnl_col in df.columns else {}
    pnl_by_regime = df.groupby("primary_regime")[pnl_col].sum().dropna().to_dict() if pnl_col in df.columns else {}
    pnl_by_bucket = df.groupby("time_bucket")[pnl_col].sum().dropna().to_dict() if pnl_col in df.columns else {}

    worst_trades = []
    best_trades = []
    if pnl_col in df.columns:
        worst_trades = df.sort_values(pnl_col, ascending=True).head(5)[["decision_id", "symbol", "strategy_id", pnl_col]].to_dict(orient="records")
        best_trades = df.sort_values(pnl_col, ascending=False).head(5)[["decision_id", "symbol", "strategy_id", pnl_col]].to_dict(orient="records")

    max_age = float(getattr(cfg, "MAX_QUOTE_AGE_SEC", 120))
    data_quality = {
        "stale_quotes": int((df["quote_age_sec"] > max_age).sum()) if "quote_age_sec" in df.columns else None,
        "missing_cross_asset": int(df["cross_asset_any_stale"].isna().sum()) if "cross_asset_any_stale" in df.columns else None,
        "high_entropy": int((df["regime_entropy"] > 1.5).sum()) if "regime_entropy" in df.columns else None,
    }

    model_usage = {}
    if "champion_model_id" in df.columns:
        model_usage = df["champion_model_id"].value_counts(dropna=True).to_dict()

    out = {
        "date": day,
        "counts": {
            "total_decisions": int(len(df)),
            "executed": executed,
            "rejected": rejected,
            "filled": filled,
            "missed": missed,
        },
        "veto_breakdown": veto_counts,
        "pnl_by_strategy": pnl_by_strategy,
        "pnl_by_regime": pnl_by_regime,
        "pnl_by_time_bucket": pnl_by_bucket,
        "worst_trades": worst_trades,
        "best_trades": best_trades,
        "data_quality": data_quality,
        "model_usage": model_usage,
    }

    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str))
    return out_path
