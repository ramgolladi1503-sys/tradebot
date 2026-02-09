import json
from pathlib import Path
import pandas as pd


def build_execution_report(df: pd.DataFrame, day: str, out_path: Path) -> Path:
    if df is None or df.empty:
        raise ValueError("Truth dataset is empty.")
    df = df.copy()
    df["ts_dt"] = pd.to_datetime(df["ts"], errors="coerce")
    df = df[df["ts_dt"].dt.date.astype(str) == day]
    if df.empty:
        raise ValueError(f"No decisions found for date {day}.")

    filled = df[df["filled_bool"] == 1]
    total = len(df)
    fill_rate = float(len(filled) / total) if total else 0.0

    time_to_fill = filled["time_to_fill_sec"].dropna()
    slippage = filled["slippage_vs_mid"].dropna()
    spread = df["spread_pct"].dropna() if "spread_pct" in df.columns else pd.Series(dtype=float)
    missed_reasons = df["missed_fill_reason"].value_counts(dropna=True).to_dict() if "missed_fill_reason" in df.columns else {}

    out = {
        "date": day,
        "fill_rate": fill_rate,
        "avg_time_to_fill": float(time_to_fill.mean()) if not time_to_fill.empty else None,
        "slippage_percentiles": {
            "p50": float(slippage.quantile(0.5)) if not slippage.empty else None,
            "p90": float(slippage.quantile(0.9)) if not slippage.empty else None,
            "p99": float(slippage.quantile(0.99)) if not slippage.empty else None,
        },
        "spread_percentiles": {
            "p50": float(spread.quantile(0.5)) if not spread.empty else None,
            "p90": float(spread.quantile(0.9)) if not spread.empty else None,
            "p99": float(spread.quantile(0.99)) if not spread.empty else None,
        },
        "missed_fill_reasons": missed_reasons,
    }
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str))
    return out_path
