import json
from pathlib import Path
import pandas as pd


def build_rl_shadow_report(df: pd.DataFrame, day: str, out_path: Path) -> Path:
    if df is None or df.empty:
        raise ValueError("Truth dataset is empty.")
    df = df.copy()
    df["ts_dt"] = pd.to_datetime(df["ts"], errors="coerce")
    df = df[df["ts_dt"].dt.date.astype(str) == day]
    if df.empty:
        raise ValueError(f"No decisions found for date {day}.")

    if "rl_suggested_multiplier" not in df.columns:
        raise ValueError("Missing rl_suggested_multiplier in truth dataset.")

    base_mult = pd.to_numeric(df["size_multiplier"], errors="coerce").fillna(1.0)
    rl_mult = pd.to_numeric(df["rl_suggested_multiplier"], errors="coerce").fillna(base_mult)
    pnl_col = "pnl_15m" if "pnl_15m" in df.columns else None
    if pnl_col is None:
        raise ValueError("Missing pnl_15m for RL counterfactual estimate.")

    pnl = pd.to_numeric(df[pnl_col], errors="coerce").fillna(0.0)
    rl_pnl_est = pnl * (rl_mult / base_mult.replace(0, 1.0))

    out = {
        "date": day,
        "baseline_qty_mean": float(pd.to_numeric(df.get("qty_planned", pd.Series(dtype=float)), errors="coerce").fillna(0).mean()),
        "rl_suggested_multiplier_mean": float(rl_mult.mean()),
        "counterfactual_pnl_sum": float(rl_pnl_est.sum()),
        "baseline_pnl_sum": float(pnl.sum()),
        "multiplier_by_regime": df.groupby("primary_regime")["rl_suggested_multiplier"].mean().dropna().to_dict(),
        "risk_guard_overrides": int((df.get("rl_shadow_only", pd.Series(dtype=float)) == 1).sum()),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str))
    return out_path
